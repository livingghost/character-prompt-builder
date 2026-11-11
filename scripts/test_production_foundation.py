"""Focused current-contract tests for diagnostics, evidence and atomic records."""
from __future__ import annotations
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import operation_context as ops
import production_store as store
from production_diagnostics import ProductionError, compare_exact

import production_fixtures


class FoundationTests(unittest.TestCase):
    def test_staged_artifacts_persist_files_then_nested_directories(self):
        from publication_artifacts import StagedArtifacts
        import stat
        with tempfile.TemporaryDirectory() as temporary:
            root = (Path(temporary) / 'staged').resolve()
            root.mkdir()
            artifacts = StagedArtifacts(root)
            synchronized = []
            original = os.fsync

            def record(descriptor):
                synchronized.append('directory' if stat.S_ISDIR(os.fstat(descriptor).st_mode) else 'file')
                original(descriptor)

            with patch.object(c.os, 'fsync', side_effect=record):
                artifacts.write('nested/first.bin', b'first exact contents')
                artifacts.write('nested/second.bin', b'second exact contents')
                self.assertEqual(synchronized, [])
                artifacts.flush_files()
                self.assertEqual(synchronized, ['file', 'file'])
                flushed = []
                flush = c.fsync_dir

                def record_directory(path):
                    flushed.append(path.relative_to(root).as_posix())
                    flush(path)

                with patch.object(c, 'fsync_dir', side_effect=record_directory):
                    artifacts.flush_directories()
            self.assertEqual(flushed, ['nested', '.'])
            self.assertEqual(artifacts.read('nested/second.bin'), b'second exact contents')
            artifacts.require_membership()

    def test_flush_failure_after_publication_reports_the_directory_as_published(self):
        import errno
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); source = base/'staged'; target = base/'published'
            source.mkdir(); (source/'result.txt').write_text('whole', encoding='utf-8')
            c.publish_directory(source, target)
            with patch.object(c, 'fsync_dir', side_effect=OSError(errno.EIO, 'Input/output error')):
                with self.assertRaises(ProductionError) as caught:
                    c.flush_published(target)
            told = caught.exception.diagnostic
            self.assertEqual((told.code, told.phase, told.file), ('ARTIFACT_PUBLISH_FAILED', 'publication', str(target)))
            self.assertEqual(told.details, {'published': True, 'actual': {'errno': errno.EIO, 'winerror': None}})
            self.assertEqual(told.required_action, c.PUBLISHED_CONTINUATION)
            self.assertEqual((target/'result.txt').read_text(encoding='utf-8'), 'whole')

    def test_directory_publication_keeps_an_existing_empty_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); source = base/'staged'; target = base/'published'
            source.mkdir(); target.mkdir(); (source/'result.txt').write_text('whole', encoding='utf-8')
            with self.assertRaisesRegex(ProductionError, 'OUTPUT_ALREADY_EXISTS'):
                c.publish_directory(source, target)
            self.assertEqual(list(target.iterdir()), [])
            self.assertEqual((source/'result.txt').read_text(encoding='utf-8'), 'whole')

    def test_directory_publication_refuses_destination_race(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); source = base/'staged'; target = base/'published'
            source.mkdir(); (source/'result.txt').write_text('whole', encoding='utf-8')
            rename = c._rename_directory_exclusive
            def race(a, b):
                b.mkdir()
                return rename(a, b)
            with patch.object(c, '_rename_directory_exclusive', side_effect=race):
                with self.assertRaisesRegex(ProductionError, 'OUTPUT_ALREADY_EXISTS'):
                    c.publish_directory(source, target)
            self.assertTrue(source.is_dir()); self.assertEqual(list(target.iterdir()), [])

    def test_directory_publication_failure_preserves_complete_staging(self):
        import errno
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); source = base/'staged'; target = base/'published'
            source.mkdir(); (source/'result.txt').write_text('whole', encoding='utf-8')
            with patch.object(c, '_rename_directory_exclusive', side_effect=OSError(errno.EIO, 'Synthetic I/O failure')):
                with self.assertRaises(ProductionError) as caught:
                    c.publish_directory(source, target)
            self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_PUBLISH_FAILED')
            self.assertEqual(caught.exception.diagnostic.phase, 'publication')
            self.assertFalse(target.exists()); self.assertTrue((source/'result.txt').is_file())

    def test_exact_diagnostic_pointer(self):
        with self.assertRaises(ProductionError) as caught:
            compare_exact({'handoff':{'targets':['purpose','decision:pose']}},{'handoff':{'targets':['purpose']}})
        self.assertEqual(caught.exception.diagnostic.pointer,'$.handoff.targets')
        self.assertEqual(caught.exception.diagnostic.code,'AUTHORIZATION_MISMATCH')

    def test_guidance_names_only_an_explicitly_declared_owner(self):
        from production_diagnostics import Diagnostic, from_exception
        error = ProductionError('PACK_DIRECTORY_NOT_ABSOLUTE', 'The pack directory must be absolute.',
                                phase='pack-selection')
        self.assertNotIn('guidance', from_exception(error, phase='cli'))
        mapped = Diagnostic('INPUT_SCHEMA_INVALID', 'The task has an invalid field.', phase='task-schema').as_dict()
        self.assertEqual(mapped['guidance'], {
            'document_path': 'references/runtime/production-preparation.md#prepare-one-complete-input',
            'schema': 'schemas/authoring/production-task.schema.json'})
        declared = {'document_path': 'references/runtime/reference-delivery.md#bind-the-actual-transport'}
        explicit = Diagnostic('INPUT_CONSISTENCY_ERROR', 'A selected transport differs.',
                              phase='selected-transport', guidance=declared).as_dict()
        self.assertEqual(explicit['guidance'], declared)

    def test_split_secret(self):
        output=io.StringIO(); secret='this-is-a-long-synthetic-secret-only'
        writer=ops.RedactingWriter(output.write,(secret,))
        for char in 'prefix '+secret+' suffix':writer.write(char)
        writer.flush(final=True)
        self.assertNotIn(secret,output.getvalue())
        self.assertIn('[REDACTED]',output.getvalue())

    def test_payload_and_auth_fields_not_duplicated(self):
        output=io.StringIO(); writer=ops.RedactingWriter(output.write,())
        document=json.dumps({'prompt':'PRIVATE WORK TEXT','api_key':'SYNTHETIC PRIVATE KEY','code':'INPUT_SCHEMA_INVALID'})
        for offset in range(0,len(document),3):writer.write(document[offset:offset+3])
        writer.flush(final=True)
        self.assertNotIn('PRIVATE WORK TEXT',output.getvalue())
        self.assertNotIn('SYNTHETIC PRIVATE KEY',output.getvalue())
        self.assertIn('INPUT_SCHEMA_INVALID',output.getvalue())

    def test_cli_stdout_is_json(self):
        with tempfile.TemporaryDirectory() as temp, production_fixtures.scratch_home(Path(temp)), contextlib.redirect_stdout(io.StringIO()) as stdout:
            def command():
                parser=ops.ArgumentParser();parser.parse_args([])
                with ops.stage('example'):print(json.dumps({'ok':True}))
                return 0
            self.assertEqual(ops.run_cli(command),0)
            self.assertEqual(json.loads(stdout.getvalue()),{'ok':True})
            rows=ops.list_operations()
            self.assertEqual(len(rows),1)
            self.assertTrue(rows[0]['complete'])
            self.assertFalse((Path(temp)/'production').exists())
            events=(Path(rows[0]['path'])/'events.jsonl').read_text(encoding='utf-8')
            self.assertIn('stage_completed',events)

    def test_argument_failure_is_logged_before_studio(self):
        with tempfile.TemporaryDirectory() as temp, production_fixtures.scratch_home(Path(temp)), contextlib.redirect_stderr(io.StringIO()):
            def command():
                parser=ops.ArgumentParser();parser.add_argument('--root',required=True);parser.parse_args([])
            self.assertEqual(ops.run_cli(command),2)
            rows=ops.list_operations(failed=True)
            self.assertEqual(len(rows),1)
            self.assertIn('argument_error',(Path(rows[0]['path'])/'events.jsonl').read_text(encoding='utf-8'))

    def test_read_only_no_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.assertEqual(store.runs(root),[])
            self.assertEqual(store.event_rows(root,'no-run'),[])
            self.assertFalse((root/'production').exists())

    def test_transaction_rolls_back_all_events(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with self.assertRaises(RuntimeError):
                with store.transaction(root):
                    store.append(root,'run',None,'authorization',{'a':1})
                    store.append(root,'run',None,'execution-created',{'a':2})
                    raise RuntimeError('synthetic interruption')
            self.assertEqual(store.event_rows(root,'run'),[])

    def test_chain_and_single_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            a=store.append(root,'run',None,'authorization',{'a':1})
            b=store.append(root,'run',None,'dispatch-claim',{'request':'a'})
            self.assertEqual(b['previous'],a['sha256'])
            with self.assertRaises(ProductionError):store.append(root,'run',None,'dispatch-claim',{'request':'b'})
            self.assertEqual(len(store.event_rows(root,'run')),2)

    def test_evidence_survives_source_deletion(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'ledger.jsonl').write_bytes(b'{"decision":"synthetic only"}\n')
            snap=store.evidence_snapshot(root,'ledger.jsonl','whole',purpose='synthetic test')
            (root/'ledger.jsonl').unlink()
            self.assertEqual(store.verify_evidence(root,snap),b'{"decision":"synthetic only"}\n')

    def test_incomplete_jsonl_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'ledger.jsonl').write_text('{"decision":', encoding='utf-8')
            with self.assertRaises(ProductionError):store.evidence_snapshot(root,'ledger.jsonl','whole',purpose='test')
            self.assertFalse((root/'production').exists())

    def test_jsonl_evidence_with_an_invalid_line_names_the_file_the_line_and_its_repair(self):
        import production_compiler as compiler
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            cases=[(b'{"decision":"first"}\n{"decision":\n{"decision":"third"}\n',2,'Expecting value'),
                   (b'{"decision":"first"}\n\n{"a":1,"a":2}\n',3,'duplicate JSON key'),
                   (b'\xff\n',1,'not UTF-8')]
            for raw,line,reason in cases:
                with self.subTest(line=line):
                    (root/'ledger.jsonl').write_bytes(raw)
                    with self.assertRaises(ProductionError) as caught:
                        store.evidence_snapshot(root,'ledger.jsonl','whole',purpose='test')
                    found=caught.exception.diagnostic.as_dict()
                    self.assertEqual((found['code'],found['file'],found['line'],found['required_action']),
                                     ('EVIDENCE_CAPTURE_FAILED','ledger.jsonl',line,store.CAPTURE_JSONL_LINE.format(line=line)))
                    self.assertIn(f'line {line} is not one JSON value',found['cause'])
                    self.assertIn(reason,found['cause'])
                    # A file a task declares reports the same line and repair as an unreadable input.
                    with self.assertRaises(ProductionError) as caught:
                        compiler.read_input(root,'ledger.jsonl',pointer='$.sources[0].path')
                    declared=caught.exception.diagnostic.as_dict()
                    self.assertEqual((declared['code'],declared['file'],declared['pointer'],declared['line'],
                                      declared['cause'],declared['required_action']),
                                     ('INPUT_UNREADABLE','ledger.jsonl','$.sources[0].path',line,found['cause'],
                                      found['required_action']))
            self.assertFalse((root/'production').exists())

    def test_a_path_that_starts_at_a_drive_or_root_is_refused_with_its_root_relative_form(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();(root/'work').mkdir()
            (root/'work/evidence.txt').write_text('evidence', encoding='utf-8')
            inside=root/'work/evidence.txt'
            for path in dict.fromkeys((inside.as_posix(),str(inside))):
                with self.subTest(path=path):
                    with self.assertRaises(ProductionError) as caught:
                        store.stable_bytes(root,path)
                    found=caught.exception.diagnostic.as_dict()
                    self.assertEqual((found['code'],found['file'],found['required_action']),
                                     ('EVIDENCE_CAPTURE_FAILED',path,store.CAPTURE_PATH_REFUSED))
                    self.assertIn('not relative to the root',found['cause'])
                    self.assertIn('below the root it is work/evidence.txt',found['cause'])
                    with self.assertRaisesRegex(ValueError,'not relative to the root'):
                        c.local(root,path)
            if os.name=='nt':
                # A drive names a place on that drive, never one below the root, with or without a separator.
                for path in (root.drive+'work/evidence.txt',root.drive+'/work/evidence.txt','/work/evidence.txt'):
                    with self.subTest(path=path),self.assertRaisesRegex(ValueError,'not relative to the root: '):
                        c.local(root,path,exists=False)
            else:
                # Elsewhere C: is an ordinary name, so the same text stays a path below the root.
                self.assertEqual(c.local(root,'C:/work/evidence.txt',exists=False),root/'C:'/'work'/'evidence.txt')
            self.assertEqual(store.stable_bytes(root,'work/evidence.txt'),b'evidence')

    def test_unread_evidence_names_its_cause_and_the_repair_that_fits_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'folder').mkdir()
            (root/'source.txt').write_text('evidence', encoding='utf-8')
            (root/'credentials.json').write_text('{}', encoding='utf-8')
            cases=[('absent.txt','missing file: absent.txt',store.CAPTURE_MISSING),
                   ('folder','directory: folder',store.CAPTURE_DIRECTORY),
                   ('credentials.json','Private Studio credentials',store.CAPTURE_PRIVATE),
                   ('folder\\source.txt','POSIX path required',store.CAPTURE_PATH_REFUSED),
                   ('../source.txt','must remain within',store.CAPTURE_PATH_REFUSED)]
            try:
                (root/'link.txt').symlink_to(root/'source.txt')
            except (OSError,NotImplementedError):
                pass
            else:
                cases.append(('link.txt','symbolic link',store.CAPTURE_PATH_REFUSED))
            for path,cause,repair in cases:
                with self.subTest(path=path),self.assertRaises(ProductionError) as caught:
                    store.stable_bytes(root,path)
                found=caught.exception.diagnostic.as_dict()
                self.assertEqual((found['code'],found['file'],found['required_action']),('EVIDENCE_CAPTURE_FAILED',path,repair))
                self.assertIn(cause,found['cause'])
            if (root/'link.txt').is_symlink():
                with self.assertRaises(ProductionError) as caught:store.stable_read(root/'link.txt','link.txt')
                self.assertEqual(caught.exception.diagnostic.required_action,store.CAPTURE_LINK)
            for error,repair in ((PermissionError(13,'Permission denied'),store.CAPTURE_DENIED),
                                 (OSError(5,'Input/output error'),store.CAPTURE_OS_ERROR)):
                with self.subTest(error=error),patch.object(Path,'open',side_effect=error), \
                        self.assertRaises(ProductionError) as caught:
                    store.stable_bytes(root,'source.txt')
                found=caught.exception.diagnostic.as_dict()
                self.assertEqual((found['required_action'],found['cause']),(repair,str(error)))
            self.assertEqual(store.stable_bytes(root,'source.txt'),b'evidence')
            self.assertFalse((root/'production').exists())

    def test_missing_evidence_reports_expected_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'source.txt').write_text('evidence', encoding='utf-8')
            snap=store.evidence_snapshot(root,'source.txt','whole',purpose='test')
            (root/'production/objects'/snap['sha256']).unlink()
            with self.assertRaises(ProductionError) as caught:store.verify_evidence(root,snap,run='run-id',event='event-id')
            self.assertEqual(caught.exception.diagnostic.details['expected'],snap['sha256'])
            self.assertEqual(caught.exception.diagnostic.details['run'],'run-id')

    def test_log_failure_does_not_disable_status(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'CPB_HOME':str(Path(temp)/'home')}):
            (Path(temp)/'home').write_text('blocked', encoding='utf-8')
            operation=ops.Operation('synthetic')
            self.assertTrue(operation.failures)
            with self.assertRaises(ProductionError):operation.durable()
            self.assertEqual(store.runs(Path(temp)),[])

    def test_staging_cleanup_does_not_follow_parent_symlink(self):
        from production_compiler import staging_cleanup
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'studio';root.mkdir()
            outside=Path(temporary)/'outside';outside.mkdir()
            (root/'production').mkdir();(root/'production/staging').symlink_to(outside,target_is_directory=True)
            (outside/'important.txt').write_text('keep', encoding='utf-8')
            with self.assertRaises(ProductionError):staging_cleanup(root,operation_id='x',apply=True)
            self.assertEqual((outside/'important.txt').read_text(encoding='utf-8'),'keep')

    def test_staging_cleanup_does_not_follow_child_symlink(self):
        from production_compiler import staging_cleanup
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'studio';parent=root/'production/staging';parent.mkdir(parents=True)
            outside=Path(temporary)/'outside';outside.mkdir()
            (outside/'owner.json').write_text(json.dumps({'operation_id':'x','pid':0}), encoding='utf-8')
            (parent/'linked').symlink_to(outside,target_is_directory=True)
            result=staging_cleanup(root,operation_id='x',apply=True)
            self.assertEqual(result['deleted'],0);self.assertTrue((outside/'owner.json').exists())

    def test_prepare_does_not_write_through_linked_staging_parent(self):
        import production_workflow as workflow
        from execution_lifecycle_smoke_test import setup
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'studio';root.mkdir()
            setup(root)
            staging=root/'production/staging';staging.rmdir()
            outside=Path(temporary)/'outside';outside.mkdir()
            staging.symlink_to(outside,target_is_directory=True)
            before=store.runs(root)
            with self.assertRaises(ValueError):workflow.prepare(root,'task.json')
            self.assertEqual(list(outside.iterdir()),[])
            self.assertEqual(store.runs(root),before)

    def test_publication_recovery_rejects_linked_run_parent(self):
        import production_compiler as compiler
        from execution_lifecycle_smoke_test import setup
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'studio';root.mkdir()
            run,_,_=setup(root)
            parent=root/'production/runs';outside=Path(temporary)/'outside'
            parent.rename(outside);parent.symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):compiler.recover_publication(root,run)
            self.assertTrue((outside/run/'prepared.json').is_file())

    def test_windows_process_probe_does_not_use_kill(self):
        import production_compiler as compiler
        with patch.object(compiler.os,'name','nt'), patch.object(compiler,'_windows_pid_active',return_value=True) as query, patch.object(compiler.os,'kill') as kill:
            self.assertTrue(compiler._pid_active(123))
            query.assert_called_once_with(123);kill.assert_not_called()


class PublicationRecoveryTests(unittest.TestCase):
    def setUp(self):
        import production_case_fixtures as fixtures
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.case = fixtures.create(base/'studio', base/'runtime')
        self.root = self.case['root']

    def interrupted_publication(self):
        import production_workflow as workflow
        with patch.object(store, 'register_run', side_effect=OSError('Synthetic registration interruption')):
            with self.assertRaises(OSError):
                workflow.prepare(self.root, 'task.json')
        self.assertEqual(store.runs(self.root), [])
        return next((self.root/'production/runs').iterdir()).name

    def test_directory_flush_failure_keeps_staging_unregistered_and_unpublished(self):
        import production_workflow as workflow
        from publication_artifacts import StagedArtifacts
        failure = OSError('Synthetic staging directory flush interruption')
        flush = StagedArtifacts.flush_directories

        def fail_run_directory(owner, **options):
            if owner.root.name.startswith('compile-'):
                raise failure
            return flush(owner, **options)

        with patch.object(StagedArtifacts, 'flush_directories', autospec=True, side_effect=fail_run_directory):
            with self.assertRaises(OSError):
                workflow.prepare(self.root, 'task.json')
        self.assertEqual(store.runs(self.root), [])
        published = self.root / 'production/runs'
        self.assertEqual(list(published.iterdir()) if published.exists() else [], [])
        staged = list((self.root / 'production/staging').iterdir())
        self.assertEqual(len(staged), 1)
        self.assertTrue((staged[0] / 'failure.json').is_file())
        self.assertTrue((staged[0] / 'manifest.json').is_file())
        self.assertTrue((staged[0] / 'prepared.json').is_file())

    def test_durable_publication_is_discoverable_and_recovered_without_reauthorization(self):
        import production_compiler as compiler
        import production_execution as execution
        import production_workflow as workflow
        run = self.interrupted_publication()
        before = execution.status(self.root)
        self.assertEqual(len(before['unregistered_publications']), 1)
        self.assertTrue(before['unregistered_publications'][0]['recoverable'])
        self.assertEqual(before['unregistered_publications'][0]['next_action'], 'recover-publication')
        # Recovery uses saved source bytes, not mutable/deletable provenance.
        (self.root/'prompt.txt').unlink()
        result = compiler.recover_publication(self.root, run)
        self.assertTrue(result['recovered'])
        document = workflow.load_run(self.root, run)[1]
        self.assertIsNone(store.authority(self.root, document['task']['task_id'], required=False))
        self.assertEqual(store.event_rows(self.root, run), [])
        self.assertFalse(compiler.recover_publication(self.root, run)['recovered'])

    def test_flush_failure_after_run_publication_names_its_registration(self):
        import errno
        import execution_contract as c
        import production_compiler as compiler
        import production_workflow as workflow
        runs = self.root / 'production/runs'
        flush = c.fsync_dir

        def refuse_the_runs_directory(path):
            if Path(path).resolve() == runs.resolve():
                raise OSError(errno.EIO, 'Input/output error', str(path))
            flush(path)

        with patch.object(c, 'fsync_dir', refuse_the_runs_directory), self.assertRaises(ProductionError) as caught:
            workflow.prepare(self.root, 'task.json')
        told = caught.exception.diagnostic
        [directory] = list(runs.iterdir())
        self.assertEqual((told.code, told.details['published'], told.file),
                         ('ARTIFACT_PUBLISH_FAILED', True, str(directory)))
        self.assertEqual(told.required_action, 'Register the published run with recover-publication --run ' + directory.name + '.')
        self.assertEqual(store.runs(self.root), [])
        self.assertTrue(compiler.recover_publication(self.root, directory.name)['recovered'])
        self.assertEqual([row['run_id'] for row in store.runs(self.root)], [directory.name])

    def test_unregistered_publication_rejects_undeclared_files_and_keeps_evidence(self):
        import production_compiler as compiler
        run = self.interrupted_publication()
        directory = self.root/'production/runs'/run
        manifest = (directory/'manifest.json').read_bytes()
        extra = directory/'unowned.txt'
        contents = b'Unowned content retained for inspection.\n'
        c.atomic(extra, contents)

        report = compiler.unregistered_publications(self.root)
        with self.assertRaises(ProductionError) as caught:
            compiler.recover_publication(self.root, run)

        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]['run'], run)
        self.assertFalse(report[0]['recoverable'])
        diagnostic = report[0]['diagnostics'][0]
        self.assertEqual(diagnostic['code'], 'ARTIFACT_SET_MISMATCH')
        self.assertEqual(diagnostic['unexpected'], ['unowned.txt'])
        self.assertEqual(diagnostic['missing'], [])
        self.assertEqual(caught.exception.diagnostic.code, 'ARTIFACT_SET_MISMATCH')
        self.assertEqual(caught.exception.diagnostic.details['unexpected'], ['unowned.txt'])
        self.assertEqual(store.runs(self.root), [])
        self.assertEqual(store.event_rows(self.root, run), [])
        self.assertEqual(extra.read_bytes(), contents)
        self.assertEqual((directory/'manifest.json').read_bytes(), manifest)

    def test_publication_consumer_digest_is_checked_before_registration(self):
        import production_compiler as compiler
        run = self.interrupted_publication()
        directory = self.root/'production/runs'/run
        consumer = c.load(directory/'consumer.json')
        consumer['instructions'] += ' Synthetic changed output.'
        (directory/'consumer.json').write_bytes(c.encoded(consumer))
        # Deliberately forge a new self-consistent manifest to exercise the
        # independent consumer commitment, not exclusive file publication.
        from publication_artifacts import ArtifactSet
        artifacts = ArtifactSet(directory, c.load(directory/'manifest.json')['files'])
        artifacts.add('consumer.json', c.encoded(consumer), replace=True)
        (directory/'manifest.json').unlink()
        compiler.write_manifest(directory, artifacts)
        report = compiler.unregistered_publications(self.root)
        self.assertFalse(report[0]['recoverable'])
        with self.assertRaises(ProductionError):
            compiler.recover_publication(self.root, run)
        self.assertEqual(store.runs(self.root), [])

    def test_recovery_requires_the_saved_runtime_content(self):
        import production_compiler as compiler
        import runtime_snapshot
        run = self.interrupted_publication()
        prepared = c.load(self.root/'production/runs'/run/'prepared.json')
        descriptor = prepared['runtime_snapshot']
        runtime_dir = runtime_snapshot.path(self.root, descriptor)
        metadata = runtime_snapshot.read(runtime_dir, descriptor)
        pack = metadata['packs'][0]
        (runtime_dir/'packs'/pack['pack_id']/pack['files'][0]['path']).unlink()
        with self.assertRaises(ProductionError) as caught:
            compiler.recover_publication(self.root, run)
        self.assertEqual(caught.exception.diagnostic.code, 'PINNED_RESOURCE_MISSING')
        self.assertEqual(store.runs(self.root), [])

    def test_work_task_mismatch_at_publication_names_both_task_ids(self):
        import production_workflow as workflow
        import work_ledger
        opened = work_ledger.require_open(self.root)
        other = {**opened, 'task_id': 'synthetic-other-work-task'}
        with patch.object(work_ledger, 'require_open', return_value=other), self.assertRaises(ProductionError) as caught:
            workflow.prepare(self.root, 'task.json')
        named = caught.exception.diagnostic.as_dict()
        self.assertEqual((named['code'], named['file'], named['pointer'], named['expected'], named['actual']),
                         ('TASK_CHANGED', 'task.json', '$.task_id', other['task_id'], opened['task_id']))
        self.assertIn('names another work task', named['message'])
        answers = iter([other])
        with patch.object(work_ledger, 'require_open', side_effect=lambda root: next(answers, opened)), \
                self.assertRaises(ProductionError) as caught:
            workflow.prepare(self.root, 'task.json')
        changed = caught.exception.diagnostic.as_dict()
        self.assertEqual((changed['code'], changed['expected'], changed['actual']),
                         ('TASK_CHANGED', other['task_id'], opened['task_id']))
        self.assertIn('changed during preparation', changed['message'])
        self.assertIn('Run the same preparing command again', changed['required_action'])
        self.assertEqual(store.runs(self.root), [])

    def test_status_reports_authority_readiness_without_creating_events(self):
        import production_execution as execution
        import production_workflow as workflow
        prepared = workflow.prepare(self.root, 'task.json')
        self.assertEqual(prepared['execution_plan']['readiness']['state'], 'authorization_required')
        state = execution.status(self.root, prepared['run'])['runs'][0]
        self.assertEqual(state['readiness'], 'authorization_required')
        self.assertEqual(state['review'], 'unreviewed')
        self.assertIn('AUTHORIZATION_REQUIRED', {row['code'] for row in state['readiness_diagnostics']})
        self.assertEqual(store.event_rows(self.root, prepared['run']), [])

    def test_bad_unreferenced_tree_does_not_hide_a_healthy_run(self):
        import production_execution as execution
        import production_workflow as workflow
        prepared = workflow.prepare(self.root, 'task.json')
        directory = self.root/'production/runs/unrecognized-publication'
        directory.mkdir()
        (directory/'manifest.json').write_text('broken', encoding='utf-8')
        report = execution.status(self.root)
        self.assertTrue(report['ok'])
        self.assertEqual(report['runs'][0]['run'], prepared['run'])
        self.assertFalse(report['unregistered_publications'][0]['recoverable'])
        self.assertTrue(report['unregistered_publications'][0]['diagnostics'])

class AuthorityEvidenceTests(unittest.TestCase):
    """Approval evidence held in a growing work ledger, and saved snapshots that go missing."""
    def setUp(self):
        import production_case_fixtures as fixtures
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.fixtures = fixtures
        self.case = fixtures.create(base/'studio', base/'runtime')
        self.root = self.case['root']
        self.task_id = self.case['task']['task_id']

    def use_ledger_as_authority_evidence(self):
        authority = c.load(self.root/'fixture-authority.json')
        authority['evidence'] = {'path': 'work/ledger.jsonl', 'locator': 'whole'}
        self.fixtures.write(self.root/'fixture-authority.json', authority)

    def prepared_run(self) -> str:
        import production_workflow as workflow
        return workflow.prepare(self.root, 'task.json')['run']

    def executed_run(self) -> str:
        run = self.prepared_run()
        self.executed_run_from(run)
        return run

    def executed_run_from(self, run: str) -> None:
        import production_execution as execution
        from test_production_execution import decisions
        result = execution.execute(self.root, run, decisions_file=decisions(self.root, run))
        self.assertTrue(result['execution_completed'])

    def test_ledger_evidence_append_does_not_invalidate_authorization(self):
        import production_workflow as workflow
        import work_ledger
        self.use_ledger_as_authority_evidence()
        run = self.prepared_run()
        work_ledger.note(self.root, 'Synthetic approval note appended after preparation; not user consent.')
        self.executed_run_from(run)
        rows = store.event_rows(self.root, run)
        submit = next(r for r in rows if r['event'] == 'authorization' and r['data']['request']['operation'] == 'submit')
        approval = submit['data']['request']['request_decision']['principal_approval']['evidence']
        captured = store.authority_record(self.root, self.task_id)['data']['evidence'][0]
        self.assertEqual((captured['path'], approval['path']), ('work/ledger.jsonl', 'work/ledger.jsonl'))
        self.assertNotEqual(captured['sha256'], approval['sha256'])
        saved = [f for f in submit['data']['files'] if (f['path'], f['sha256']) == (approval['path'], approval['sha256'])]
        self.assertEqual([(f['purpose'], f['locator']) for f in saved], [('principal-approval', 'whole')])
        self.assertTrue(saved[0]['captured_at'])
        # Another append changes provenance only; both saved readings stay intact.
        work_ledger.note(self.root, 'Synthetic later note; not user consent.')
        report = workflow.impact(self.root, run)
        self.assertTrue(report['ok'], report['changes'])
        self.assertIn(('work/ledger.jsonl', 'provenance_changed', 'intact'),
                      {(x['path'], x['status'], x['snapshot']) for x in report['provenance']})

    def test_an_authorization_without_a_saved_reading_it_cites_names_a_new_authorization(self):
        import copy
        import production_execution as execution
        import production_request
        import production_workflow as workflow
        import work_ledger
        from test_production_execution import decisions
        self.use_ledger_as_authority_evidence()
        run = self.prepared_run()
        work_ledger.note(self.root, 'Synthetic approval note appended after preparation; not user consent.')
        loaded = workflow.read_run(self.root, run)
        plan = loaded.artifacts['execution-plan.json']
        execution.authorize_decisions(self.root, run, decisions(self.root, run), loaded.prepared, plan)
        directory, prepared, _, rows = workflow.load_run(self.root, run)
        submit = next(r for r in rows if r['event'] == 'authorization' and r['data']['request']['operation'] == 'submit')
        approval = submit['data']['request']['request_decision']['principal_approval']['evidence']
        # An authorization record that saved no reading of the approval it cites.
        data = copy.deepcopy(submit['data'])
        data['files'] = [item for item in data['files'] if item.get('purpose') != 'principal-approval']
        unsaved = workflow.append_record(directory, prepared, rows, 'authorization', data)
        intent = next(item for item in plan['operations'] if item['operation'] == 'submit')
        with self.assertRaises(ProductionError) as caught:
            workflow._permission(self.root, prepared, store.event_rows(self.root, run), unsaved['sha256'], **intent)
        found = caught.exception.diagnostic.as_dict()
        self.assertEqual((found['code'], found['run'], found['event'], found['file'], found['expected']),
                         ('EVIDENCE_SNAPSHOT_MISSING', run, unsaved['sha256'], approval['path'], approval['sha256']))
        self.assertEqual(found['required_action'], production_request.UNSAVED_AUTHORIZATION_EVIDENCE.format(run=run))
        self.assertNotEqual(found['required_action'], store.RESTORE_EVIDENCE)
        # An authorization that the decisions file recorded saved the reading, and execution uses it.
        self.assertTrue(execution.execute(self.root, run)['execution_completed'])

    def test_issuer_update_error_identifies_the_editable_field_and_current_authority(self):
        self.prepared_run()
        prior = store.authority_record(self.root, self.task_id)
        document = store.authority(self.root, self.task_id)
        issuer = document['issuer']
        document['issuer'] = 'Another principal'
        self.fixtures.write(self.root/'amended-authority.json', document)
        with self.assertRaises(ProductionError) as caught:
            store.import_authority(self.root, 'amended-authority.json', expected=prior['sha256'])
        diagnostic = caught.exception.diagnostic
        self.assertEqual((diagnostic.file, diagnostic.pointer), ('amended-authority.json', '/issuer'))
        self.assertEqual(diagnostic.details['expected'], issuer)
        self.assertEqual(diagnostic.details['current_authority']['event'], prior['sha256'])
        self.assertIn('--expected-event ' + prior['sha256'], diagnostic.required_action)
        self.assertEqual(store.authority_record(self.root, self.task_id), prior)
        document['issuer'] = issuer
        self.fixtures.write(self.root/'amended-authority.json', document)
        changed = store.import_authority(self.root, 'amended-authority.json', expected=prior['sha256'])
        self.assertEqual(changed['data']['authority']['issuer'], issuer)

    def test_missing_run_snapshot_names_run_event_digest_and_restoration(self):
        import production_workflow as workflow
        run = self.executed_run()
        rows = store.event_rows(self.root, run)
        receipt = next(r for r in rows if r['event'] == 'authorization')
        missing = receipt['data']['files'][0]
        (workflow.run_dir(self.root, run)/'objects'/missing['sha256']).unlink()
        with self.assertRaises(ProductionError) as caught:
            workflow.load_run(self.root, run)
        diagnostic = caught.exception.diagnostic
        self.assertEqual(diagnostic.code, 'EVIDENCE_SNAPSHOT_MISSING')
        self.assertEqual(diagnostic.details['run'], run)
        self.assertEqual(diagnostic.details['event'], receipt['sha256'])
        self.assertEqual(diagnostic.details['expected'], missing['sha256'])
        self.assertEqual(diagnostic.file, missing['path'])
        self.assertEqual(diagnostic.required_action, store.RESTORE_EVIDENCE)
        self.assertEqual(diagnostic.details['impact'], store.RUN_EVIDENCE_IMPACT)

    def test_missing_authority_snapshot_stops_authorization_with_restoration(self):
        self.prepared_run()
        record = store.authority_record(self.root, self.task_id)
        lost = record['data']['evidence'][0]
        (self.root/'production/objects'/lost['sha256']).unlink()
        with self.assertRaises(ProductionError) as caught:
            store.authority(self.root, self.task_id)
        diagnostic = caught.exception.diagnostic
        self.assertEqual(diagnostic.code, 'EVIDENCE_SNAPSHOT_MISSING')
        self.assertEqual(diagnostic.details['event'], record['sha256'])
        self.assertEqual(diagnostic.details['expected'], lost['sha256'])
        self.assertEqual(diagnostic.details['source'], lost['path'])
        self.assertEqual(diagnostic.required_action, store.RESTORE_EVIDENCE)
        self.assertEqual(diagnostic.details['impact'], store.AUTHORITY_EVIDENCE_IMPACT)

    def test_latest_run_comes_from_registration_not_the_work_projection(self):
        import work_ledger
        from pack_manager import generate_uuid7
        first = self.prepared_run()
        task = c.load(self.root/'task.json')
        second_series = dict(task, production_id=generate_uuid7())
        self.fixtures.write(self.root/'second.json', second_series)
        import production_workflow as workflow
        second = workflow.prepare(self.root, 'second.json')['run']
        # A stale projection does not move the formal answer.
        current = work_ledger.read_current(self.root)
        current['production_run'] = first
        work_ledger.write_current(self.root, current)
        self.assertEqual(store.latest_run(self.root, self.task_id), second)
        self.assertEqual(store.latest_run(self.root, self.task_id, production_id=task['production_id']), first)
        self.assertEqual(store.latest_run(self.root, self.task_id, production_id=second_series['production_id']), second)
        self.assertIsNone(store.latest_run(self.root, 'another-task'))

    def test_authorization_records_protected_criteria(self):
        import production_fixtures
        import production_workflow as workflow
        run = self.prepared_run()
        document = store.authority(self.root, self.task_id)
        document['grants'][0]['protected_criteria'] = ['output']
        self.fixtures.write(self.root/'protected.json', document)
        store.import_authority(self.root, 'protected.json', expected=store.authority_record(self.root, self.task_id)['sha256'])
        directory, prepared, _, _ = workflow.load_run(self.root, run)
        plan = c.load(directory/'execution-plan.json')
        intent = next(item for item in plan['operations'] if item['operation'] == 'direction')
        token = production_fixtures.grant(self.root, run, intent)
        row = workflow.find(store.event_rows(self.root, run), 'authorization', token)
        criterion = next(x for x in prepared['task']['criteria'] if x['id'] == 'output')
        self.assertEqual(row['data']['protected_criteria'], {'ids': ['output'], 'sha256': c.content_id([criterion])})


class SchemaDocumentContextTests(unittest.TestCase):
    def test_full_schema_document_reused_only_within_one_validation(self):
        import state_protocol as protocol
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            schema_path = root/'item.json'
            schema_path.write_text('{"type":"integer"}', encoding='utf-8')
            schema = {'type':'array','items':{'$ref':'item.json'}}
            original_read = Path.read_bytes
            reads = []
            def read(path):
                if path == schema_path:
                    reads.append(path)
                return original_read(path)
            with patch.object(protocol,'SCHEMA_DIR',root), patch.object(Path,'read_bytes',read):
                self.assertEqual(protocol.validate_against_schema([1]*50,schema),[])
                self.assertEqual(len(reads),1)
                self.assertTrue(protocol.validate_against_schema([1,'wrong'],schema))
                self.assertEqual(len(reads),2)
                metadata = schema_path.stat()
                schema_path.write_text('{"type":"string" }', encoding='utf-8')
                os.utime(schema_path,ns=(metadata.st_atime_ns,metadata.st_mtime_ns))
                self.assertEqual(schema_path.stat().st_size,metadata.st_size)
                self.assertEqual(protocol.validate_against_schema(['now-a-string'],schema),[])
                self.assertEqual(len(reads),3)

class AggregateInputTests(unittest.TestCase):
    def setUp(self):
        import production_case_fixtures as fixture
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name);self.case=fixture.create(base/'studio',base/'runtime',with_upscale=True)
        self.root=self.case['root'];self.fixture=fixture
    def check(self):
        import production_compiler as compiler
        report=compiler.check_task(self.root,'task.json')
        self.assertEqual(store.runs(self.root),[])
        self.assertEqual(store.event_rows(self.root,'unused'),[])
        return report
    def break_recording(self):
        task=c.load(self.root/'task.json');task['recording']['character']='missing-character'
        self.fixture.write(self.root/'task.json',task)
    def test_independent_recording_and_model_parameter_errors_are_both_reported(self):
        self.break_recording();parameters=c.load(self.root/'parameters.json');parameters['steps']=-1
        self.fixture.write(self.root/'parameters.json',parameters)
        report=self.check();self.assertFalse(report['publishable'])
        self.assertIn('recording-validation',{x['phase'] for x in report['diagnostics']})
        self.assertTrue(any(x['file']=='parameters.json' and 'below minimum' in x['message'] for x in report['diagnostics']))
        self.assertTrue(any(x['phase']=='execution-controls' and x['state']=='failed' for x in report['checks']))
    def test_multiple_bad_controls_each_have_a_specific_pointer(self):
        self.break_recording();parameters=c.load(self.root/'parameters.json')
        parameters.update(steps=-1,width=-2,height=-3);self.fixture.write(self.root/'parameters.json',parameters)
        report=self.check();errors=[row for row in report['diagnostics'] if row['phase']=='execution-controls']
        self.assertEqual({row['pointer'] for row in errors},{'$.steps','$.width','$.height'})
        self.assertEqual({row['file'] for row in errors},{'parameters.json'})
        self.assertFalse(report['publishable'])
    def test_reading_retrieval_and_parameters_are_not_hidden_by_recording(self):
        self.break_recording();task=c.load(self.root/'task.json')
        reading=c.load(self.root/task['route_reading']);reading['documents'][0]['sha256']='0'*64
        self.fixture.write(self.root/task['route_reading'],reading)
        record=c.load(self.root/'retrieval.json');record['settled']=False;self.fixture.write(self.root/'retrieval.json',record)
        parameters=c.load(self.root/'parameters.json');parameters['steps']=-1;self.fixture.write(self.root/'parameters.json',parameters)
        report=self.check();phases={x['phase'] for x in report['diagnostics']}
        self.assertTrue({'route-reading','retrieval','execution-controls','recording-validation'}<=phases,report)
    def test_missing_prompt_blocks_only_dependent_checks(self):
        self.break_recording();(self.root/'prompt.txt').unlink()
        report=self.check();self.assertFalse(report['publishable'])
        self.assertTrue(any(x['code']=='RECORDING_CONTRACT_INVALID' for x in report['diagnostics']))
        blocked={k for x in report['diagnostics'] for k in x['blocked_checks']}
        self.assertIn('retrieval',blocked);self.assertIn('render-intent',blocked)
        self.assertTrue(any(x['phase']=='target-contract' and x['state']=='passed' for x in report['checks']))
        self.assertTrue(any(x['phase']=='execution-controls' and x['state']=='passed' for x in report['checks']))
    def test_missing_reference_file_does_not_hide_bad_output_recording(self):
        from prepare_generation_references import prepare_references
        from PIL import Image
        path=self.root/'palette.png';Image.new('RGB',(32,32)).save(path)
        references=prepare_references([{'role':'palette','source':{'kind':'supplied-file','reference_id':'synthetic-palette',
            'resolved_path':str(path)}}],model=self.fixture.MODEL_ID,output_dir=self.root/'reference-preparation')
        self.fixture.write(self.root/'references.json',references)
        task=c.load(self.root/'task.json');task['generation']['references']='references.json'
        task['recording']['character']='missing-character';self.fixture.write(self.root/'task.json',task)
        path.unlink()
        report=self.check()
        failed={row['phase'] for row in report['checks'] if row['state']=='failed'}
        self.assertTrue({'recording-validation','reference-preparation'}<=failed,report)
        self.assertFalse(report['publishable'])

    def test_negative_and_recording_errors_are_both_exposed(self):
        self.break_recording();task=c.load(self.root/'task.json')
        self.fixture.write(self.root/'negative.txt','Synthetic exclusion.')
        task['generation'].update(negative='negative.txt',negative_transport='integrated-critical')
        self.fixture.write(self.root/'task.json',task)
        report=self.check();phases={x['phase'] for x in report['diagnostics']}
        self.assertTrue({'negative-transport','recording-validation'}<=phases,report)
    def test_upscale_parameter_error_is_independent_of_recording(self):
        import production_compiler as compiler
        name=self.fixture.upscale_task(self.root);task=c.load(self.root/name)
        request=c.load(self.root/task['delivery']['path']);request['scale_factor']=3
        self.fixture.write(self.root/task['delivery']['path'],request)
        task['recording']['character']='missing-character';self.fixture.write(self.root/name,task)
        report=compiler.check_task(self.root,name);self.assertFalse(report['publishable'])
        self.assertTrue({'recording-validation','execution-controls'}<={x['phase'] for x in report['diagnostics']},report)
        self.assertTrue(any(x['code']=='CONTROL_NOT_AVAILABLE' and x['pointer']=='$.scale_factor' for x in report['diagnostics']))
        self.assertEqual(store.runs(self.root),[])
    def test_input_changed_after_its_capture_is_not_published(self):
        import production_workflow as workflow
        snapshot=workflow.snapshot
        def race(*args,**kwargs):
            parameters=c.load(self.root/'parameters.json');parameters['steps']=21
            self.fixture.write(self.root/'parameters.json',parameters)
            return snapshot(*args,**kwargs)
        with patch.object(workflow,'snapshot',side_effect=race):
            with self.assertRaises(ProductionError) as caught:
                workflow.prepare(self.root,'task.json')
        diagnostic=caught.exception.diagnostic
        self.assertEqual((diagnostic.code,diagnostic.file,diagnostic.phase),('SOURCE_CHANGED','parameters.json','publication'))
        self.assertNotEqual(diagnostic.details['expected'],diagnostic.details['actual'])
        self.assertEqual(store.runs(self.root),[])
    def test_each_declared_input_is_read_once_per_compilation(self):
        import collections
        import production_compiler as compiler
        counts=collections.Counter();read=store.stable_bytes
        def counting(root,path):
            counts[path]+=1
            return read(root,path)
        with patch.object(store,'stable_bytes',side_effect=counting):
            self.assertTrue(compiler.check_task(self.root,'task.json')['publishable'])
        task=c.load(self.root/'task.json')
        declared=['task.json',task['delivery']['path'],task['route_reading'],*(s['path'] for s in task['sources']),
                  *(task['generation'][name] for name in ('parameters','production_spec','plot','retrieval_record','creative_intent'))]
        self.assertEqual({path:counts[path] for path in declared},{path:1 for path in declared})
    def test_failed_prepare_adds_no_formal_run(self):
        import production_workflow as workflow
        self.break_recording()
        with self.assertRaises(ProductionError):workflow.prepare(self.root,'task.json')
        self.assertEqual(store.runs(self.root),[])
    def test_actual_scope_evidence_failure_does_not_hide_parameter_failure(self):
        self.break_recording();task=c.load(self.root/'task.json');authority=c.load(self.root/task['authority'])
        (self.root/authority['evidence']['path']).unlink()
        report=self.check();self.assertTrue(any(x['phase']=='authority-evidence' and x['state']=='failed' for x in report['checks']))
        self.assertIn('recording-validation',{x['phase'] for x in report['diagnostics']})


class CompilerContractTests(unittest.TestCase):
    """Check reports every independent problem with its code, file and pointer, and writes nothing."""
    def setUp(self):
        import production_case_fixtures as fixtures
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.fixtures=fixtures
        self.case=fixtures.create(self.base/'studio',self.base/'runtime');self.root=self.case['root']
    def check(self,task='task.json'):
        import production_compiler as compiler
        return compiler.check_task(self.root,task)
    def edit(self,name,change):
        value=c.load(self.root/name);change(value);self.fixtures.write(self.root/name,value)
    def case_with(self,change,**options):
        """A new synthetic case whose pack records are changed before anything reads them."""
        import pack_manager
        create=self.fixtures.create_pack
        def changed(path,**kwargs):
            result=create(path,**kwargs);document=c.load(path/'records/models.json')
            change(document['records']);self.fixtures.write(path/'records/models.json',document);pack_manager.write_lock(path)
            return result
        base=self.base/('case-'+str(len(list(self.base.iterdir()))))
        with patch.object(self.fixtures,'create_pack',side_effect=changed):
            return self.fixtures.create(base/'studio',base/'runtime',**options)
    def coded(self,report):
        return {(row['code'],row['pointer']) for row in report['diagnostics']}

    def test_successful_check_changes_no_file(self):
        import glob
        def files():
            found={str(path):c.sha256_file(path) for path in self.root.rglob('*') if path.is_file()}
            found['state']=c.sha256_file(self.case['settings'].state_file)
            return found
        # The shared system temp directory contains other concurrently running
        # compiler checks. Observe this operation's private scratch area only.
        with tempfile.TemporaryDirectory(dir=self.base) as scratch:
            temporary=lambda:set(glob.glob(str(Path(scratch)/'cpb-check-*')))
            before,staged=files(),temporary()
            with patch.object(tempfile,'tempdir',scratch):
                report=self.check()
            self.assertTrue(report['publishable'],report['diagnostics'])
            self.assertEqual(files(),before)
            self.assertEqual(temporary(),staged)
            self.assertEqual(store.runs(self.root),[])

    def test_check_and_prepare_outputs_follow_their_schemas(self):
        import production_compiler as compiler
        import production_workflow as workflow
        report=self.check()
        compiler.validate_document(report,compiler.REPORT_SCHEMA,'compilation report')
        self.assertIsNone(report['run']);self.assertIsNone(report['execution_plan']['run'])
        self.edit('parameters.json',lambda value:value.update(steps=-1))
        failed=self.check()
        compiler.validate_document(failed,compiler.REPORT_SCHEMA,'compilation report')
        self.edit('parameters.json',lambda value:value.update(steps=20))
        prepared=workflow.prepare(self.root,'task.json')
        compiler.validate_document(prepared['execution_plan'],compiler.PLAN_SCHEMA,'execution plan')
        self.assertEqual(prepared['execution_plan']['run'],prepared['run'])
        recorded=compiler.published_preparation(self.root,prepared['run'])
        self.assertEqual(c.encoded({**recorded,'formal_run_created':True}),c.encoded(prepared))
        self.assertFalse(recorded['formal_run_created'])
        self.assertEqual([row['run_id'] for row in store.runs(self.root)],[prepared['run']])

    def test_selected_integrated_text_survives_check_and_prepare(self):
        import production_compiler as compiler
        import production_workflow as workflow
        def integrated_model(records):
            records[0].update(negative_transport_mode='integrated-critical',supports_negative_prompt=False,
                              max_positive_prompt_chars=40,max_negative_prompt_chars=4)
        root=self.case_with(integrated_model)['root']
        integrated='A flat graphic robot. No text.'
        self.fixtures.write(root/'integrated.txt',integrated)
        self.fixtures.write(root/'negative.txt','Unwanted lettering and malformed anatomy.')
        task=c.load(root/'task.json')
        task['generation'].update(integrated_prompt='integrated.txt',negative='negative.txt')
        self.fixtures.write(root/'task.json',task)
        self.assertGreater(len((root/'prompt.txt').read_text(encoding='utf-8')),40)
        checked=compiler.check_task(root,'task.json')
        self.assertTrue(checked['publishable'],checked['diagnostics'])
        self.assertIn({'phase':'negative-transport','state':'passed'},
                      [{'phase':row['phase'],'state':row['state']} for row in checked['checks']])
        self.assertEqual(checked['request_preview']['prompt'],integrated)
        self.assertNotIn('negative_prompt',checked['request_preview'])
        prepared=workflow.prepare(root,'task.json')
        self.assertEqual(prepared['request_preview']['prompt'],integrated)
        self.assertNotIn('negative_prompt',prepared['request_preview'])
        package=c.load(Path(prepared['package']))
        self.assertEqual(package['generation_payload']['transports']['integrated']['text'],integrated)
        self.assertEqual(package['generation_payload']['negative_prompt'],'Unwanted lettering and malformed anatomy.')

    def test_native_preflight_uses_the_selected_negative_with_or_without_a_portable_alternative(self):
        import production_compiler as compiler
        def native_model(records):
            records[0].update(negative_transport_mode='native-subset',max_negative_prompt_chars=4)
        for portable in ('Unwanted lettering and malformed anatomy.',None):
            with self.subTest(portable=portable):
                root=self.case_with(native_model)['root']
                self.fixtures.write(root/'native.txt','text')
                task=c.load(root/'task.json');task['generation']['native_negative']='native.txt'
                if portable is not None:
                    self.fixtures.write(root/'negative.txt',portable)
                    task['generation']['negative']='negative.txt'
                self.fixtures.write(root/'task.json',task)
                report=compiler.check_task(root,'task.json')
                self.assertTrue(report['publishable'],report['diagnostics'])
                self.assertEqual(report['request_preview']['negative_prompt'],'text')
                self.assertEqual(report['request_preview']['prompt'],self.fixtures.PROMPT)
                self.assertEqual(store.runs(root),[])

    def test_selected_text_limits_fail_during_preflight(self):
        import production_compiler as compiler
        for mode,field in (('integrated-critical','integrated_prompt'),('native-subset','native_negative')):
            with self.subTest(mode=mode):
                def limited_model(records):
                    records[0].update(negative_transport_mode=mode,supports_negative_prompt=mode=='native-subset',
                                      max_negative_prompt_chars=4)
                    if mode=='integrated-critical':records[0]['max_positive_prompt_chars']=40
                root=self.case_with(limited_model)['root']
                self.fixtures.write(root/'selected.txt','A selected text that exceeds the declared channel character limit.')
                task=c.load(root/'task.json');task['generation'][field]='selected.txt'
                self.fixtures.write(root/'task.json',task)
                report=compiler.check_task(root,'task.json')
                self.assertFalse(report['publishable'])
                self.assertTrue(any(row['phase']=='negative-transport' and 'limit' in row['message']
                                    for row in report['diagnostics']),report['diagnostics'])
                self.assertEqual(store.runs(root),[])

    def test_task_schema_error_blocks_only_checks_that_need_the_task(self):
        self.edit('task.json',lambda task:task['criteria'][0].pop('text'))
        self.edit('parameters.json',lambda value:value.update(steps=-1))
        report=self.check()
        self.assertIn('task-schema',{row['phase'] for row in report['diagnostics'] if row['code']=='INPUT_SCHEMA_INVALID'})
        self.assertTrue(any(row['phase']=='execution-controls' and row['pointer']=='$.steps' for row in report['diagnostics']))
        states={row['phase']:row['state'] for row in report['checks']}
        self.assertEqual((states['task-contract'],states['recording-validation']),('not-performed','not-performed'))
        self.assertEqual((states['plot'],states['retrieval'],states['target-contract']),('passed','passed','passed'))

    def test_unreadable_input_keeps_its_file_pointer_and_cause(self):
        self.edit('task.json',lambda task:task['generation'].update(plot='missing/plot.json',creative_intent='inputs\\intent.json'))
        report=self.check()
        unreadable={row['pointer']:row for row in report['diagnostics'] if row['code']=='INPUT_UNREADABLE'}
        self.assertEqual(unreadable['$.generation.plot']['file'],'missing/plot.json')
        self.assertIn('missing file',unreadable['$.generation.plot']['cause'])
        self.assertIn('POSIX',unreadable['$.generation.creative_intent']['cause'])
        self.assertEqual(unreadable['$.generation.plot']['required_action'],store.CAPTURE_MISSING)
        self.assertEqual(unreadable['$.generation.creative_intent']['required_action'],store.CAPTURE_PATH_REFUSED)
        self.assertIn('/ separators',store.CAPTURE_PATH_REFUSED)
        states={row['phase']:row['state'] for row in report['checks']}
        self.assertEqual((states['plot'],states['retrieval']),('not-performed','not-performed'))
        self.assertEqual(states['execution-controls'],'passed')

    def test_a_check_that_did_not_run_names_the_failed_prerequisite_to_resolve_first(self):
        from production_diagnostics import DEFAULT_ACTION
        self.edit('task.json',lambda task:task['generation'].update(plot='missing/plot.json'))
        report=self.check()
        waiting={row['phase']:row for row in report['diagnostics'] if row['code']=='CHECK_NOT_PERFORMED'}
        # A check names the prerequisite it waits for; one waiting behind another also names the failed one.
        self.assertEqual(waiting['plot']['blocked_by'],['input:$.generation.plot'])
        self.assertIn('Resolve the error of the input at $.generation.plot first',waiting['plot']['required_action'])
        self.assertEqual((waiting['retrieval']['blocked_by'],waiting['retrieval']['failed_prerequisites']),
                         (['plot'],['input:$.generation.plot']))
        self.assertIn('Resolve the error of the input at $.generation.plot first',waiting['retrieval']['required_action'])
        self.assertIn('check retrieval runs once it passes',waiting['retrieval']['required_action'])
        failed={row['phase'] for row in report['diagnostics']
                if row['code']!='CHECK_NOT_PERFORMED' and row['severity']=='error'}
        self.assertEqual(set(waiting['compilation']['blocked_by']),failed)
        missing=self.check('missing-task.json')['diagnostics']
        unread=next(row for row in missing if row['code']=='INPUT_UNREADABLE')
        task_read=next(row for row in missing if row['code']=='CHECK_NOT_PERFORMED' and row['phase']=='task-read')
        self.assertEqual((unread['phase'],task_read['blocked_by']),('task-read',['task-read']))
        self.assertIn('Resolve the error of task-read first',task_read['required_action'])
        for row in [*waiting.values(),*(row for row in missing if row['code']=='CHECK_NOT_PERFORMED')]:
            self.assertNotEqual(row['required_action'],DEFAULT_ACTION)

    def test_unavailable_controls_and_missing_profiles_have_their_own_codes(self):
        import production_compiler as compiler
        self.edit('parameters.json',lambda value:value.update(cfgScale=7,strength=0.5))
        self.assertTrue({('CONTROL_NOT_AVAILABLE','$.cfgScale'),('CONTROL_NOT_AVAILABLE','$.strength')}<=self.coded(self.check()))
        def without_profile(records):
            del records[0]['offerings'][0]['execution_profile']
        report=compiler.check_task(self.case_with(without_profile)['root'],'task.json')
        self.assertIn('MODEL_PROFILE_MISSING',{row['code'] for row in report['diagnostics'] if row['phase']=='execution-profile'})
        self.assertFalse(report['publishable'])

    def test_upscale_offering_without_a_scale_key_fails_at_check(self):
        import production_compiler as compiler
        def without_scale_key(records):
            next(record for record in records if record['id']==self.fixtures.UPSCALE_MODEL_ID)['offerings'][0].pop('parameter_keys')
        root=self.case_with(without_scale_key,with_upscale=True)['root']
        report=compiler.check_task(root,self.fixtures.upscale_task(root))
        self.assertIn(('MODEL_PROFILE_MISSING','$.scale_factor'),self.coded(report))
        self.assertFalse(report['publishable'])

    def test_unknown_upscale_request_factors_leave_the_scale_to_the_offering_profile(self):
        import production_compiler as compiler
        for name,change in (('absent',lambda record:record.pop('supported_scale_factors')),
                            ('null',lambda record:record.update(supported_scale_factors=None))):
            with self.subTest(supported_scale_factors=name):
                def unknown(records):
                    change(next(record for record in records if record['id']==self.fixtures.UPSCALE_MODEL_ID))
                root=self.case_with(unknown,with_upscale=True)['root']
                task=self.fixtures.upscale_task(root)
                report=compiler.check_task(root,task)
                self.assertTrue(report['publishable'],report['diagnostics'])
                delivery=c.load(root/task)['delivery']['path']
                request=c.load(root/delivery);request['scale_factor']=3;self.fixtures.write(root/delivery,request)
                refused=compiler.check_task(root,task)
                errors=[row for row in refused['diagnostics'] if row['code']!='CHECK_NOT_PERFORMED']
                self.assertEqual({(row['code'],row['phase'],row['file'],row['pointer']) for row in errors},
                                 {('CONTROL_NOT_AVAILABLE','execution-controls',delivery,'$.scale_factor')})
                # The repair names where the offering's execution profile declares the allowed factors.
                self.assertIn('the schema of the scale control in modes.upscale.controls of the execution_profile '
                              'of the synthetic offering in model record '+self.fixtures.UPSCALE_MODEL_ID,
                              errors[0]['required_action'])
                self.assertIn('scale factor 3',errors[0]['message'])
                self.assertFalse(refused['publishable'])

    def test_bounded_views_and_scene_material_are_compiler_checks(self):
        states={row['phase']:row['state'] for row in self.check()['checks']}
        self.assertEqual([states[name] for name in ('world-views','moment-views','scene-materials')],['passed']*3)
        self.assertTrue({'source-validation','package-compilation','request-compilation','execution-plan'}<=set(states))

    def test_missing_dependency_is_reported_for_reference_tasks(self):
        from prepare_generation_references import prepare_references
        from transport_synthetic import _png
        import reference_runtime
        c.atomic(self.root/'palette.png',_png(32,32,b'\x50\x78\xa0'))
        references=prepare_references([{'role':'palette','source':{'kind':'supplied-file','reference_id':'synthetic-palette',
            'resolved_path':str(self.root/'palette.png')}}],model=self.fixtures.MODEL_ID,output_dir=self.root/'reference-preparation')
        self.fixtures.write(self.root/'references.json',references)
        self.edit('task.json',lambda task:task['generation'].update(references='references.json'))
        with patch.object(reference_runtime,'preflight_dependencies',side_effect=ImportError('No module named synthetic_dependency')):
            report=self.check()
        found=[row for row in report['diagnostics'] if row['phase']=='dependency-preflight']
        self.assertEqual([row['code'] for row in found],['DEPENDENCY_UNAVAILABLE'])
        from cli_invocation import shown
        skill_root=Path(__file__).resolve().parents[1]
        self.assertIn(shown(['uv','sync','--locked','--project',str(skill_root)]),found[0]['required_action'])
        self.assertIn(shown(['uv','run','--locked','--project',str(skill_root),'python',
                             str(skill_root/'scripts/check_dependencies.py')]),found[0]['required_action'])
        self.assertEqual({row['phase']:row['state'] for row in report['checks']}['reference-preparation'],'not-performed')

    def test_no_reference_preparation_publishes_no_reference_companion(self):
        import production_workflow as workflow
        run=workflow.prepare(self.root,'task.json')['run']
        directory=workflow.run_dir(self.root,run)
        self.assertFalse((directory/'package.references').exists())
        self.assertEqual(c.load(directory/'request-contract.json')['media'],[])

    def test_mutable_fields_declare_form_requirement_and_compiler_checks(self):
        import production_workflow as workflow
        fields=workflow.prepare(self.root,'task.json')['execution_plan']['mutable_fields']
        keys={'description','schema','required','nullable','value_form','document_type','checks','rebuild','protected_criteria'}
        self.assertEqual({name for name,field in fields.items() if set(field)!=keys},set())
        phases={row['phase'] for row in self.check()['checks']}
        declared={name for field in fields.values() for name in field['checks']}
        self.assertEqual(declared-phases,{'dependency-preflight','reference-preparation','negative-provenance'})
        self.assertEqual({key:fields['references'][key] for key in ('value_form','document_type','nullable','required')},
                         {'value_form':'studio-file','document_type':'prepared-reference-set','nullable':True,'required':False})
        self.assertEqual((fields['count']['protected_criteria'],fields['direction']['protected_criteria'],fields['prompt']['protected_criteria']),
                         ('unchanged','redefine','recheck'))
        self.assertIn('source-validation',fields['state-lineage']['checks']);self.assertNotIn('retrieval',fields['state-lineage']['checks'])

    def test_sheet_slot_conditions_are_checked_at_prepare(self):
        import production_workflow as workflow
        from production_diagnostics import CompilationError
        for name,recording,expected in (('panel.json',{'sheet_panel':False,'subject_map':{'robot':'robot'}},('RECORDING_CONTRACT_INVALID','$.recording.sheet_panel')),
                                        ('mapping.json',{'sheet_panel':True,'subject_map':{}},('SHEET_SUBJECT_MAPPING_MISSING','$.recording.subject_map'))):
            with self.subTest(name=name):
                task=c.load(self.root/'task.json');task['recording'].update(slot='canon.primary',**recording)
                self.fixtures.write(self.root/name,task)
                with self.assertRaises(CompilationError) as caught:
                    workflow.prepare(self.root,name)
                self.assertIn(expected,self.coded(caught.exception.report))
        self.assertEqual(store.runs(self.root),[])


class ExitCodeTests(unittest.TestCase):
    def test_each_diagnostic_class_has_its_exit_status(self):
        from production_diagnostics import exit_code, result_exit
        self.assertEqual([exit_code(code) for code in (None, 'INPUT_SCHEMA_INVALID', 'SOURCE_CHANGED', 'AUTHORIZATION_REQUIRED',
                                                       'REMOTE_OUTCOME_UNKNOWN')],
                         [0, 2, 2, 3, 4])
        rows = lambda *codes: [{'code': code, 'severity': 'error'} for code in codes]
        self.assertEqual(result_exit(rows('GRANT_REVOKED', 'INPUT_UNREADABLE')), 2)
        self.assertEqual(result_exit(rows('GRANT_REVOKED', 'DISPATCH_ALREADY_CLAIMED')), 4)
        self.assertEqual(result_exit(rows('PACK_RUNTIME_REQUIRED', 'CHECK_NOT_PERFORMED')), 3)
        self.assertEqual(result_exit([], failure=4), 4)


class CleanupTests(unittest.TestCase):
    """Cleanup removes only an ended owner's unclaimed journal or unrecoverable publication."""
    def setUp(self):
        import production_case_fixtures as fixtures
        import subprocess, sys
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name);self.root=fixtures.create(base/'studio',base/'runtime')['root']
        ended=subprocess.Popen([sys.executable,'-c','pass']);ended.wait();self.dead=ended.pid

    def test_unclaimed_journal_is_removed_only_for_its_owner(self):
        from production_compiler import staging_cleanup
        journal=self.root/'runs/01a10000-0000-7000-8000-000000000001'
        journal.mkdir(parents=True)
        (journal/'run.json').write_bytes(c.encoded({'production_run':None,'owner':{'operation_id':'op-journal','pid':self.dead},
                                                     'at':'2000-01-01T00:00:00Z'}))
        listed=staging_cleanup(self.root)['journals']
        self.assertEqual([(item['name'],item['eligible']) for item in listed],[(journal.name,True)])
        other=staging_cleanup(self.root,operation_id='op-other',apply=True)
        self.assertEqual((other['deleted'],other['journals'][0]['reasons'][-1]),(0,'owned by a different operation'))
        self.assertTrue(journal.is_dir())
        removed=staging_cleanup(self.root,operation_id='op-journal',apply=True)
        self.assertEqual(removed['deleted'],1);self.assertFalse(journal.exists())

    def test_only_an_unrecoverable_publication_is_removable(self):
        import production_compiler as compiler
        import production_workflow as workflow
        with patch.object(store,'register_run',side_effect=OSError('Synthetic registration interruption')):
            with self.assertRaises(OSError):workflow.prepare(self.root,'task.json')
        directory=next((self.root/'production/runs').iterdir())
        (directory/'owner.json').write_bytes(c.encoded({'operation_id':'op-publication','pid':self.dead}))
        recoverable=compiler.staging_cleanup(self.root,operation_id='op-publication',apply=True)['publications'][0]
        self.assertEqual((recoverable['eligible'],recoverable['reasons']),(False,['recoverable: register it with recover-publication']))
        consumer=c.load(directory/'consumer.json');consumer['instructions']+=' Synthetic damage.'
        (directory/'consumer.json').write_bytes(c.encoded(consumer))
        listed=compiler.staging_cleanup(self.root)['publications'][0]
        self.assertTrue(listed['eligible'])
        self.assertEqual(compiler.staging_cleanup(self.root,operation_id='op-publication',apply=True)['deleted'],1)
        self.assertFalse(directory.exists());self.assertEqual(store.runs(self.root),[])

    def test_damaged_manifest_of_an_unregistered_publication_names_its_removal(self):
        import production_compiler as compiler
        import production_workflow as workflow
        with patch.object(store,'register_run',side_effect=OSError('Synthetic registration interruption')):
            with self.assertRaises(OSError):workflow.prepare(self.root,'task.json')
        directory=next((self.root/'production/runs').iterdir())
        (directory/'owner.json').write_bytes(c.encoded({'operation_id':'op-publication','pid':self.dead}))
        manifest=c.load(directory/'manifest.json');repeated=manifest['files'][0]
        manifest['files'].append(dict(repeated))
        (directory/'manifest.json').write_bytes(c.encoded(manifest))
        with self.assertRaises(ProductionError) as caught:compiler.recover_publication(self.root,directory.name)
        found=caught.exception.diagnostic.as_dict()
        self.assertEqual((found['code'],found['path'],found['required_action']),
                         ('ARTIFACT_MANIFEST_CORRUPT',repeated['path'],compiler.UNRECOVERABLE_PUBLICATION))
        self.assertEqual(Path(found['file']).name,directory.name)
        listed=compiler.staging_cleanup(self.root)['publications'][0]
        self.assertEqual((listed['eligible'],listed['diagnostics'][0]['required_action']),
                         (True,compiler.UNRECOVERABLE_PUBLICATION))
        self.assertEqual(compiler.staging_cleanup(self.root,operation_id='op-publication',apply=True)['deleted'],1)
        self.assertFalse(directory.exists());self.assertEqual(store.runs(self.root),[])

    def test_a_registered_manifest_that_is_not_a_complete_file_array_names_no_staging_cleanup(self):
        import sqlite3
        from contextlib import closing
        import production_compiler as compiler
        import production_workflow as workflow
        run=workflow.prepare(self.root,'task.json')['run']
        directory=workflow.run_dir(self.root,run);manifest=c.load(directory/'manifest.json')
        for code,change in (('ARTIFACT_INCOMPLETE',{'complete':False}),('ARTIFACT_MANIFEST_CORRUPT',{'files':{}})):
            with self.subTest(code=code):
                # The registration records exactly these manifest bytes.
                raw=c.encoded({**manifest,**change});(directory/'manifest.json').write_bytes(raw)
                with closing(sqlite3.connect(self.root/'production/records.sqlite3')) as db:
                    db.execute('UPDATE runs SET manifest_sha256=? WHERE run_id=?',(c.digest(raw),run));db.commit()
                with self.assertRaises(ProductionError) as caught:workflow.read_run(self.root,run,force=True)
                found=caught.exception.diagnostic.as_dict()
                self.assertEqual((found['code'],found['run'],Path(found['file']),found['required_action']),
                                 (code,run,directory/'manifest.json',compiler.REGISTERED_MANIFEST_DAMAGED))
                self.assertEqual(compiler.staging_cleanup(self.root)['publications'],[])

    def test_predecessor_comes_from_formal_records(self):
        import production_workflow as workflow
        import work_ledger
        with patch.object(work_ledger,'write_current',side_effect=OSError('Synthetic projection failure')):
            first=workflow.prepare(self.root,'task.json')
        self.assertEqual(first['warnings'][0]['code'],'WORK_PROJECTION_FAILED')
        second=workflow.prepare(self.root,'task.json')
        self.assertEqual(workflow.load_run(self.root,second['run'])[1]['predecessor'],first['run'])


class ImplementationPinTests(unittest.TestCase):
    """A run pins the modules that compile and execute import, never tests or release metadata."""
    def test_an_index_written_for_other_sources_is_refused(self):
        import execution_contract as c
        import production_workflow as workflow
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in ('scripts','schemas','config'):(root/name).mkdir()
            module=root/'scripts/alpha.py';module.write_bytes(b'VALUE = 1\n')
            (root/'schemas/alpha.schema.json').write_bytes(b'{}\n')
            index={'files':sorted(['scripts/alpha.py','schemas/alpha.schema.json',workflow.IMPLEMENTATION_INDEX]),
                   'sources':{'scripts/alpha.py':c.sha256_file(module)}}
            (root/workflow.IMPLEMENTATION_INDEX).write_bytes(c.encoded(index))
            with patch.object(workflow,'ROOT',root):
                self.assertEqual(workflow.implementation_files(),index['files'])
                module.write_bytes(b'VALUE = 2\n')
                with self.assertRaises(ProductionError) as caught:workflow.implementation_files()
                self.assertEqual((caught.exception.diagnostic.code,caught.exception.diagnostic.file),('IMPLEMENTATION_CHANGED','scripts/alpha.py'))
                self.assertIn('rebuild_metadata.py',caught.exception.diagnostic.required_action)
                module.write_bytes(b'VALUE = 1\n')
                (root/'schemas/beta.schema.json').write_bytes(b'{}\n')
                with self.assertRaises(ProductionError) as caught:workflow.implementation_files()
                self.assertEqual((caught.exception.diagnostic.code,caught.exception.diagnostic.file),('IMPLEMENTATION_CHANGED','schemas'))

    def test_rewritten_test_file_keeps_the_run_current_and_a_module_change_is_named(self):
        import shutil
        import production_case_fixtures as fixtures
        import production_workflow as workflow
        files=workflow.implementation_files()
        # The committed index is the import closure of the current sources.
        self.assertEqual(files,workflow.implementation_closure())
        self.assertIn(workflow.IMPLEMENTATION_INDEX,files)
        self.assertTrue({'scripts/production_compiler.py','scripts/production_execution.py','scripts/catalog_retrieval/runtime.py'}<=set(files))
        self.assertEqual([path for path in files if Path(path).name.startswith('test_') or path.endswith('_smoke_test.py')],[])
        self.assertNotIn('package-manifest.toml',files)
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);root=fixtures.create(base/'studio',base/'runtime')['root']
            run=workflow.prepare(root,'task.json')['run']
            pinned=[d for d in workflow.load_run(root,run)[1]['dependencies'] if d['space']=='skill']
            copied=base/'installation'
            for item in pinned+[{'path':'scripts/test_production_foundation.py'}]:
                target=copied/item['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(workflow.ROOT/item['path'],target)
            with patch.object(workflow,'ROOT',copied):
                test_file=copied/'scripts/test_production_foundation.py'
                test_file.write_bytes(test_file.read_bytes()+b'\n# A later test edit.\n')
                workflow.assert_current(root,run)
                module=copied/'scripts/production_compiler.py'
                module.write_bytes(module.read_bytes()+b'\n')
                # The prepared run keeps its sealed request: a changed installation is a notice.
                current=workflow.read_current(root,run)
            [notice]=[item for item in current.notices if item['code']=='IMPLEMENTATION_CHANGED']
            self.assertEqual((notice['severity'],notice['phase'],notice['file']),
                             ('warning','implementation','scripts/production_compiler.py'))
            self.assertNotIn('changed_files',notice)
            with patch.object(workflow,'ROOT',copied):
                other=copied/'scripts/production_execution.py'
                other.write_bytes(other.read_bytes()+b'\n')
                problems,found=workflow.freshness(root,run)
            self.assertEqual(problems,[])
            changed=[item for item in found if item['code']=='IMPLEMENTATION_CHANGED']
            # One update of the installation is one notice, whatever its file count.
            self.assertEqual(len(changed),1)
            self.assertEqual(sorted(row['path'] for row in changed[0]['changed_files']),
                             ['scripts/production_compiler.py','scripts/production_execution.py'])
            self.assertEqual(changed[0]['file'],changed[0]['changed_files'][0]['path'])
            for row,pin in ((row,next(d for d in pinned if d['path']==row['path'])) for row in changed[0]['changed_files']):
                self.assertEqual(row['expected'],pin['sha256'])
                self.assertNotEqual(row['actual'],pin['sha256'])


class RecordingDestinationTests(unittest.TestCase):
    """Execute rechecks the recording slot; a lost destination never discards captured bytes."""
    def setUp(self):
        import production_case_fixtures as fixtures
        import production_workflow as workflow
        import studio
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name);self.fixtures=fixtures
        self.root=fixtures.create(base/'studio',base/'runtime')['root']
        self.run=workflow.prepare(self.root,'task.json')['run']
        self.decisions=fixtures.fill_decisions(self.root,self.run,'decisions.json')
        self.home=studio.character_dir(self.root,'robot');self.away=base/'moved-character'

    def test_execute_stops_before_execution_claim_when_the_slot_changed(self):
        import production_execution as execution
        import execution_lifecycle as accounting
        sheet=self.home/'sheet/sheet-data.json';original=sheet.read_bytes()
        # A new declared panel changes the destination's production contract;
        # merely registering an ordinary scene does not declare a panel.
        profile=c.load(Path(__file__).resolve().parents[1]/'templates/character-sheet-layout.general.json')
        profile['rows'][0]['boxes'][0]['aliases']=['candidate']
        profile_path=self.root/'revised-sheet-profile.json'
        self.fixtures.write(profile_path,profile)
        document=c.load(sheet);document['fields']['field.sheet_layout_profile']=str(profile_path)
        self.fixtures.write(sheet,document)
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root,self.run,decisions_file=self.decisions)
        self.assertEqual((caught.exception.diagnostic.code,caught.exception.diagnostic.pointer),('RECORDING_CONTRACT_INVALID','$.recording.sheet_panel'))
        sheet.write_bytes(original)
        self.home.rename(self.away)
        with self.assertRaises(ProductionError) as caught:
            execution.execute(self.root,self.run,decisions_file=self.decisions)
        self.assertEqual(caught.exception.diagnostic.code,'RECORDING_CONTRACT_INVALID')
        self.assertEqual(accounting.all_states(self.root),[])
        self.assertEqual(execution.unclaimed_journals(self.root),[])

    def test_projection_failure_and_lost_destination_keep_the_captured_candidates(self):
        import production_execution as execution
        import studio
        with patch.object(studio,'iterate',side_effect=OSError('Synthetic Studio write failure')):
            result=execution.execute(self.root,self.run,decisions_file=self.decisions)
        item=result['runs'][0]
        self.assertEqual((item['capture'],item['registration'],item['next_action']['command']),('complete','projection-missing','resume'))
        self.assertEqual(len(item['candidates']),1)
        self.home.rename(self.away)
        item=execution.status(self.root,self.run)['runs'][0]
        self.assertEqual((item['capture'],item['registration'],len(item['candidates'])),('complete','unregistered',1))
        self.assertEqual(item['next_action']['command'],'resume');self.assertIn('robot/candidate is missing',item['next_action']['reason'])
        self.away.rename(self.home)
        resumed=execution.resume(self.root,self.run)['runs'][0]
        self.assertEqual((resumed['registration'],resumed['candidates']),('registered',item['candidates']))


class ExactValueTests(unittest.TestCase):
    def test_booleans_cannot_stand_for_authorized_numbers(self):
        for expected,actual in [(1,True),(0,False),(1,1.0),({'x':1},{'x':True})]:
            with self.subTest(expected=expected,actual=actual),self.assertRaises(ProductionError):
                compare_exact(expected,actual)
    def test_nested_array_diagnostic_names_the_element(self):
        with self.assertRaises(ProductionError) as caught:
            compare_exact({'layers':[{'strength':1}]},{'layers':[{'strength':True}]})
        self.assertEqual(caught.exception.diagnostic.pointer,'$.layers[0].strength')
    def test_reordered_objects_are_equal_but_array_order_is_semantic(self):
        compare_exact({'a':1,'b':2},{'b':2,'a':1})
        with self.assertRaises(ProductionError):compare_exact([1,2],[2,1])
    def test_cached_digest_does_not_skip_current_root_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);root=base/'studio';root.mkdir();path=root/'data.json';path.write_bytes(b'{}')
            os.utime(path,ns=(1_000_000_000,1_000_000_000))
            c.file_digest(root,'data.json');root.rename(base/'saved');root.symlink_to(base/'saved',target_is_directory=True)
            with self.assertRaises(ValueError):c.file_digest(root,'data.json')
    def test_cached_root_cannot_hide_a_redirected_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);root=base/'studio';root.mkdir();(root/'payload.txt').write_bytes(b'original')
            c.local(root,'payload.txt');root.rename(base/'saved')
            other=base/'other';other.mkdir();(other/'payload.txt').write_bytes(b'unrelated')
            root.symlink_to(other,target_is_directory=True)
            with self.assertRaises(ValueError):c.local(root,'payload.txt')


class StudioPathTests(unittest.TestCase):
    RELATIVE='a/b/c/data.json'

    def new_studio(self,base:Path)->Path:
        root=base/'studio';(root/'a/b/c').mkdir(parents=True)
        path=root/self.RELATIVE;path.write_bytes(b'{"a":1}');os.utime(path,ns=(1_000_000_000,1_000_000_000))
        return root

    def test_a_symbolic_link_at_each_depth_is_refused_after_a_reused_reading(self):
        parts=self.RELATIVE.split('/')
        for depth in range(1,len(parts)+1):
            with self.subTest(depth=depth),tempfile.TemporaryDirectory() as temporary:
                root=self.new_studio(Path(temporary))
                self.assertEqual(c.file_digest(root,self.RELATIVE),(c.digest(b'{"a":1}'),7))
                entry=root.joinpath(*parts[:depth]);moved=entry.with_name(entry.name+'-moved')
                entry.rename(moved);entry.symlink_to(moved,target_is_directory=moved.is_dir())
                for exists in (True,False):
                    with self.assertRaisesRegex(ValueError,'symbolic link in studio path'):c.local(root,self.RELATIVE,exists=exists)
                with self.assertRaisesRegex(ValueError,'symbolic link in studio path'):c.file_digest(root,self.RELATIVE)

    def test_a_swapped_directory_and_a_rewritten_file_are_hashed_again(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);root=self.new_studio(base)
            c.file_digest(root,self.RELATIVE)
            (root/'a').rename(base/'earlier');(root/'a/b/c').mkdir(parents=True)
            swapped=root/self.RELATIVE;swapped.write_bytes(b'{"a":2}');os.utime(swapped,ns=(1_000_000_000,1_000_000_000))
            self.assertEqual(c.file_digest(root,self.RELATIVE),(c.digest(b'{"a":2}'),7))
            swapped.write_bytes(b'{"a":3}')
            self.assertEqual(c.file_digest(root,self.RELATIVE),(c.digest(b'{"a":3}'),7))

    def test_each_entry_is_read_once_and_nothing_is_resolved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=self.new_studio(Path(temporary));expected=c.file_digest(root,self.RELATIVE)
            entries=[str(root),*(str(root.joinpath(*self.RELATIVE.split('/')[:n])) for n in range(1,5))]
            for call,answer in ((lambda:c.local(root,self.RELATIVE),root/self.RELATIVE),(lambda:c.file_digest(root,self.RELATIVE),expected)):
                with patch('os.lstat',wraps=os.lstat) as lstat,patch.object(Path,'resolve',side_effect=AssertionError('resolved')),\
                        patch.object(c,'read',side_effect=AssertionError('read')):
                    self.assertEqual(call(),answer)
                self.assertEqual([os.fspath(x.args[0]) for x in lstat.call_args_list],entries)
            self.assertEqual(c.local(root,'a/absent/new.json',exists=False),root/'a/absent/new.json')
            with self.assertRaisesRegex(ValueError,'missing file: a/b/absent.json'):c.local(root,'a/b/absent.json')

    @unittest.skipUnless(os.name=='nt','directory junctions are a Windows feature')
    def test_a_junction_staying_inside_is_accepted_and_one_leaving_is_refused(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);root=self.new_studio(base)
            outside=base/'outside';outside.mkdir();(outside/'data.json').write_bytes(b'{"a":9}')
            for link,target in ((root/'inner',root/'a/b'),(root/'a/outer',outside)):
                made=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True)
                if made.returncode!=0:self.skipTest('this file system makes no directory junction')
            self.assertEqual(c.local(root,'inner/c/data.json'),root/'inner/c/data.json')
            self.assertEqual(c.local(root,'inner/c/new.json',exists=False),root/'inner/c/new.json')
            self.assertEqual(c.file_digest(root,'inner/c/data.json'),(c.digest(b'{"a":1}'),7))
            for relative,exists in (('a/outer/data.json',True),('a/outer/new.json',False)):
                with self.assertRaises(ValueError):c.local(root,relative,exists=exists)
            with self.assertRaises(ValueError):c.file_digest(root,'a/outer/data.json')

    @unittest.skipUnless(os.name=='nt','Windows trims a trailing dot or space from a name')
    def test_a_name_windows_trims_takes_the_full_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=self.new_studio(Path(temporary))
            for relative in ('.../data.json','a/.. /data.json',' /data.json'):
                with self.subTest(relative=relative),self.assertRaises(ValueError):c.local(root,relative,exists=False)
            self.assertEqual(c.local(root,'a/b./c/data.json',exists=False),root/'a/b./c/data.json')

    def test_a_root_whose_ancestor_became_a_link_is_refused_after_a_recheck(self):
        with tempfile.TemporaryDirectory() as temporary:
            holder=Path(temporary)/'holder';root=self.new_studio(holder)
            self.assertEqual(c.local(root,self.RELATIVE),root/self.RELATIVE)
            moved=holder.with_name('holder-moved');holder.rename(moved);holder.symlink_to(moved,target_is_directory=True)
            c.recheck_roots()
            with self.assertRaisesRegex(ValueError,'symbolic link in root'):c.local(root,self.RELATIVE)

    def test_the_step_before_an_external_effect_checks_root_ancestry_first(self):
        import production_workflow as workflow
        import execution_lifecycle as lifecycle
        calls=[]
        class Stop(Exception):pass
        def assert_current(root,run,*,force=False,previous_runtime=None):
            calls.append(('assert_current',force));raise Stop
        with tempfile.TemporaryDirectory() as temporary,\
                patch.object(c,'recheck_roots',side_effect=lambda:calls.append('recheck_roots')),\
                patch.object(workflow,'assert_current',side_effect=assert_current),self.assertRaises(Stop):
            lifecycle.begin_step(Path(temporary),'run','authorization',claim='claim',step='send',operation='send')
        self.assertEqual(calls,['recheck_roots',('assert_current',True)])


class SchemaEqualityTests(unittest.TestCase):
    def test_boolean_cannot_satisfy_numeric_constant_or_enum(self):
        from state_protocol import validate_against_schema as validate
        for value,schema in [(True,{'const':1}),(False,{'enum':[0,1]}),({'x':True},{'const':{'x':1}}),([False],{'enum':[[0]]})]:
            with self.subTest(value=value): self.assertTrue(validate(value,schema))
    def test_unique_schema_items_use_instance_equality(self):
        from state_protocol import validate_against_schema as validate
        self.assertTrue(validate([1,1.0],{'uniqueItems':True}))
        self.assertEqual(validate([True,1],{'uniqueItems':True}),[])
    def test_schema_numeric_equality_is_not_byte_representation_equality(self):
        from state_protocol import validate_against_schema as validate
        self.assertEqual(validate(1.0,{'const':1}),[])
        self.assertEqual(validate({'x':1.0},{'enum':[{'x':1}]}),[])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
