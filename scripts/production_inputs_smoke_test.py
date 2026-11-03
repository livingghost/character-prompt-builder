#!/usr/bin/env python3
"""Exercise authored input assembly with local synthetic sources and no provider."""
from __future__ import annotations

import copy
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
from input_evidence import InputEvidence
import production_inputs as tool
import production_input_adapters as adapters
import route_reading as reading
from private_state import PrivateStateError


class PrivateAuthenticationInputTests(unittest.TestCase):
    """Private Studio state stops at each ordinary input publication boundary."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / 'credentials.json'
        self.raw = c.encoded({'synthetic-service': {'api_key': 'synthetic-private-value'}})
        self.private.write_bytes(self.raw)

    def test_ordinary_io_preserves_private_file_and_exposes_no_digest(self):
        calls = (
            lambda: c.local(self.root, self.private.name),
            lambda: c.read(self.private),
            lambda: c.load(self.private),
            lambda: c.sha256_file(self.private),
            lambda: c.file_digest(self.root, self.private.name),
            lambda: c.atomic(self.private, b'ordinary replacement', replace=True),
        )
        for call in calls:
            with self.subTest(operation=call), self.assertRaises(PrivateStateError):
                call()
        self.assertEqual(self.private.read_bytes(), self.raw)
        self.assertEqual([path.name for path in self.root.iterdir()], ['credentials.json'])

    def test_private_temporary_and_case_variants_have_the_same_boundary(self):
        for name in ('.pending-auth-synthetic', 'CREDENTIALS.JSON', 'credentials.json.',
                     'credentials.json::$DATA'):
            with self.subTest(name=name), self.assertRaises(PrivateStateError):
                c.atomic(self.root / name, self.raw)
            self.assertEqual({path.name for path in self.root.iterdir()}, {'credentials.json'})
        ordinary = self.root / 'credentials-guide.json'
        c.atomic(ordinary, c.encoded({'subject': 'credentials'}))
        self.assertEqual(c.load(ordinary), {'subject': 'credentials'})

    def test_live_and_named_root_inputs_capture_no_private_bytes(self):
        readers = (
            (InputEvidence(self.root), 'credentials.json'),
            (InputEvidence(None, named_roots={'@skill': self.root}), '@skill/credentials.json'),
        )
        for inputs, path in readers:
            with self.subTest(path=path), self.assertRaises(PrivateStateError):
                inputs.read({'path': path, 'sha256': c.digest(self.raw)})
            self.assertEqual(inputs.snapshots, {})
            self.assertEqual(inputs.read_paths, set())

    def test_captured_input_contract_refuses_private_state(self):
        snapshots = {'credentials.json': {'sha256': c.digest(self.raw), 'size': len(self.raw),
                                         'base64': base64.b64encode(self.raw).decode('ascii')}}
        with self.assertRaises(PrivateStateError):
            InputEvidence(None, snapshots=snapshots, live=False)

    def test_evidence_read_and_preverified_bytes_publish_no_object(self):
        import production_store as store
        from production_diagnostics import ProductionError
        with self.assertRaises(ProductionError):
            store.stable_bytes(self.root, 'credentials.json')
        with self.assertRaises(ProductionError):
            store.stable_read(self.private, 'selected-input.json')
        calls = (
            lambda: store.evidence_snapshot(self.root, 'credentials.json', 'whole', purpose='synthetic', raw=self.raw),
            lambda: store.capture_evidence(self.root, self.root / 'run', 'credentials.json',
                                          locator='whole', purpose='synthetic', raw=self.raw),
        )
        for call in calls:
            with self.subTest(operation=call), self.assertRaises(PrivateStateError):
                call()
        self.assertFalse((self.root / 'production').exists())
        self.assertFalse((self.root / 'run').exists())

    def test_iteration_copy_refuses_private_file_and_companion_before_copy(self):
        import studio
        home = self.root / 'characters/synthetic'
        with self.assertRaises(PrivateStateError):
            studio._keep(self.root, home, 'it-0001', self.private, 'request')
        companion = self.root / 'source.references'
        companion.mkdir()
        (companion / 'ordinary.txt').write_text('Synthetic ordinary input.', encoding='utf-8')
        (companion / 'credentials.json').write_bytes(self.raw)
        with self.assertRaises(PrivateStateError):
            studio._keep_companion(home, 'it-0001', companion)
        self.assertFalse(home.exists())
        self.assertEqual(self.private.read_bytes(), self.raw)

    def test_saved_private_source_is_refused_before_review_attachment(self):
        import artifact_review
        import production_store as store
        snapshot = {'path': 'credentials.json', 'sha256': c.digest(self.raw), 'size': len(self.raw)}
        files = {}
        with patch.object(c, 'object_read', side_effect=AssertionError('private object read')):
            with self.assertRaises(PrivateStateError):
                artifact_review._object_file(self.root, snapshot, files)
        with self.assertRaises(PrivateStateError):
            store.verify_evidence(self.root, snapshot)
        self.assertEqual(files, {})

    def test_operation_artifact_registration_refuses_private_metadata(self):
        import operation_context as operations
        with patch.dict(os.environ, {'CPB_HOME': str(self.root / 'private-runtime')}):
            operation = operations.Operation('synthetic-private-input-check')
            try:
                with patch.object(operations.hashlib, 'file_digest', side_effect=AssertionError('private bytes read')):
                    with self.assertRaises(PrivateStateError):
                        operation.artifact(self.private)
                self.assertEqual(operation.artifacts, {})
            finally:
                operation.finish(0)

class InputToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task = {'task_id': 'synthetic-task', 'route': 'development', 'features': [],
                     'sources': [], 'delivery': {'path': 'delivery.txt',
                     'translation_notes': 'Retain the synthetic authored delivery.'},
                     'criteria': [{'id': 'output', 'text': 'Inspect the actual local text.', 'strength': 'hard', 'evidence': 'text'}],
                     'route_reading': 'reading.json'}
        self.task.update(artifact='text', execution='authored', production_id='01900000-0000-7000-8000-000000000010')
        self.task.update(authority='authority.json', world_views=[], direction={'purpose': 'Synthetic local task.',
            'intended_effect': 'Synthetic output, not an audience claim.', 'basis': [], 'decisions': [],
            'action_slice': None, 'limitations': ['Synthetic input fixture.']})
        (self.root / 'task.json').write_bytes(c.encoded(self.task))
        (self.root / 'delivery.txt').write_text('Synthetic authored delivery.\n', encoding='utf-8')
        self.ledger = self.root / 'work/reads.jsonl'
        self.env = patch.dict(os.environ, {'CPB_READS_LEDGER': str(self.ledger)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.issued = reading.issue('development', studio=self.root, ledger=self.ledger,
                                    stream=io.StringIO(), key='1' * 32, at='2000-01-01T00:00:00Z')
        manifest, bodies = reading.capture('development')
        always = set(c.load(reading.ROOT / reading.execution_routes.MANIFEST)['always_read'])
        applied = []
        for meta, raw in bodies:
            if meta['kind'] != 'document' or meta['path'] in always:
                continue
            paragraph = next(block for block in reading.prose_blocks(raw.decode()) if len(block.split()) >= 12)
            applied.append({'path': meta['path'], 'quote': paragraph,
                            'why': 'Synthetic operator applies this source to the local development exercise.'})
        self.choices = tool.draft_choices(self.task)
        self.choices['reading']['reading_key'] = self.issued['reading_key']
        self.choices['reading']['applied'] = applied
        self.save_choices()

    def save_choices(self):
        (self.root / 'choices.json').write_bytes(c.encoded(self.choices))

    def files(self):
        # WAL/checkpoint coordination can change physical SQLite pages during a
        # read. Compare every committed table/row, plus every other file byte,
        # instead of treating that coordination as a new Production event.
        import production_store
        database = production_store.database(self.root)
        physical = {database, Path(str(database) + '-wal'), Path(str(database) + '-shm')}
        result = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*')
                  if p.is_file() and p not in physical}
        with production_store.reader(self.root) as connection:
            if connection is not None:
                result['production/records.sqlite3:committed-content'] = '\n'.join(connection.iterdump()).encode('utf-8')
        return result

    def build(self, output='built'):
        return tool.build_inputs(self.root, 'task.json', 'choices.json', output)

    def test_inspection_is_read_only(self):
        before = self.files()
        result = tool.inspect_inputs(self.root, 'task.json')
        self.assertEqual(result['state'], 'inspection')
        self.assertEqual(self.files(), before)
        self.assertFalse(result['authority']['eligibility_evaluated'])

    def test_draft_keeps_judgments_unanswered(self):
        result = tool.draft_inputs(self.root, 'task.json', 'draft')
        draft = c.load(self.root / result['choices_file'])
        self.assertIsNone(draft['reading']['reading_key'])
        self.assertIsNone(draft['visual'])
        self.assertIsNone(draft['validation'])
        self.assertTrue(result['unresolved'])
        self.assertNotIn('clear', json.dumps(draft))

    def test_missing_choices_publish_nothing(self):
        self.choices = tool.draft_choices(self.task)
        self.save_choices()
        before = self.files()
        result = self.build()
        self.assertFalse(result['ok'])
        self.assertIn('reading.reading_key', [x['field'] for x in result['unresolved']])
        self.assertFalse((self.root / 'built').exists())
        self.assertEqual(self.files(), before)

    def test_build_derives_document_hashes(self):
        before_task = (self.root / 'task.json').read_bytes()
        result = self.build()
        self.assertTrue(result['ok'])
        ref = result['inputs']['route-reading']
        raw = c.read(self.root / ref['path'])
        self.assertEqual(c.digest(raw), ref['sha256'])
        record = c.decode(raw)
        self.assertEqual(record['documents'], self.issued['row']['documents'])
        self.assertEqual(record['applied'], self.choices['reading']['applied'])
        reading.require_route_reading(record, studio=self.root)
        self.assertEqual((self.root / 'task.json').read_bytes(), before_task)
        self.assertEqual(c.load(self.root / 'built/production-task.json')['route_reading'], 'built/route-reading.json')
        self.assertFalse((self.root / 'production').exists())
        self.assertFalse(result['external_effect'])

    def test_empty_why_is_not_completed(self):
        self.choices['reading']['applied'][0]['why'] = ''
        self.save_choices()
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse((self.root / 'built').exists())

    def test_quotation_is_not_replaced(self):
        self.choices['reading']['applied'][0]['quote'] = 'Synthetic fabricated sentence absent from the selected source document and its complete original contents.'
        self.save_choices()
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse((self.root / 'built').exists())

    def test_caller_supplied_document_hashes_are_refused(self):
        self.choices['reading']['documents'] = []
        self.save_choices()
        with self.assertRaises(ValueError):
            self.build()

    def test_incomplete_continuity_names_its_field(self):
        self.choices['visual'] = {'subjects': {'person': {'continuity': None}}}
        self.save_choices()
        result = self.build()
        self.assertEqual(result['unresolved'], [{'field': 'visual.subjects.person.continuity',
                                               'code': 'continuity-choice-required'}])
        self.assertFalse((self.root / 'built').exists())

    def test_failed_specialist_publishes_no_partial_inputs(self):
        with patch.object(adapters, 'build_validation', side_effect=ValueError('Synthetic invalid evidence')):
            with self.assertRaises(ValueError):
                self.build()
        self.assertFalse((self.root / 'built').exists())

    def test_existing_destination_is_preserved(self):
        (self.root / 'built').mkdir()
        (self.root / 'built/authored.txt').write_text('Preserve this existing synthetic source.', encoding='utf-8')
        before = self.files()
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(self.files(), before)

    def test_build_rechecks_choices_bytes_before_publication(self):
        original = adapters.build_validation
        def altered(*args):
            result = original(*args)
            (self.root / 'choices.json').write_text('{}', encoding='utf-8')
            return result
        with patch.object(adapters, 'build_validation', side_effect=altered):
            with self.assertRaises(ValueError):
                self.build()
        self.assertFalse((self.root / 'built').exists())
        self.assertFalse(list(self.root.glob('.production-inputs-*')))

    def test_failed_publish_cleans_staging(self):
        with patch.object(c, 'publish_directory', side_effect=OSError('Synthetic rename failure')):
            with self.assertRaises(OSError):
                self.build()
        self.assertFalse((self.root / 'built').exists())
        self.assertFalse(list(self.root.glob('.production-inputs-*')))

    def test_task_choices_cannot_replace_authority(self):
        self.choices['task_changes'] = {'authority': 'fabricated-authority.json'}
        self.save_choices()
        with self.assertRaises(ValueError):
            self.build()

    def test_reusing_key_does_not_issue_another_key(self):
        before = self.ledger.read_bytes()
        self.build('first')
        self.build('second')
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_conflicting_issuance_is_refused(self):
        altered = copy.deepcopy(self.issued['row'])
        altered['documents'][0]['sha256'] = 'f' * 64
        self.ledger.write_bytes(self.ledger.read_bytes() + c.encoded(altered))
        with self.assertRaises(ValueError):
            self.build()

    def test_resolving_key_cannot_invent_issuance(self):
        self.choices['reading']['reading_key'] = '2' * 32
        self.save_choices()
        with self.assertRaises(ValueError):
            self.build()

    def test_corrupt_ledger_is_not_skipped(self):
        self.ledger.write_bytes(self.ledger.read_bytes() + b'{broken\n')
        with self.assertRaises(ValueError):
            self.build()

    def test_unrelated_issuance_keeps_existing_record(self):
        reading.issue('development', studio=self.root, ledger=self.ledger, stream=io.StringIO(), key='3' * 32)
        self.assertTrue(self.build()['ok'])

    def test_context_does_not_fill_unanswered_choices(self):
        draft = tool.draft_inputs(self.root, 'task.json', 'draft')
        context = c.load(self.root / draft['context_file'])
        context['unresolved'] = []
        (self.root / draft['context_file']).write_bytes(c.encoded(context))
        result = tool.build_inputs(self.root, 'task.json', draft['choices_file'], 'built')
        self.assertFalse(result['ok'])
        self.assertTrue(result['unresolved'])

    def test_edit_file_contains_choices_and_context_is_separate(self):
        draft = tool.draft_inputs(self.root, 'task.json', 'draft')
        document = c.load(self.root / draft['choices_file'])
        self.assertEqual(set(document), {'reading', 'visual', 'validation', 'task_changes', 'external'})
        self.assertEqual(c.load(self.root / draft['context_file'])['task_content'], self.task)
        (self.root / draft['choices_file']).write_bytes(c.encoded(self.choices))
        self.assertTrue(tool.build_inputs(self.root, 'task.json', draft['choices_file'], 'built')['ok'])

    def test_output_path_cannot_escape_studio(self):
        with self.assertRaises(ValueError):
            self.build('../escaped')

    def dispatcher_task(self, route='development'):
        task = copy.deepcopy(self.task)
        task.update(artifact='image', execution='dispatcher', route=route)
        (self.root / 'task.json').write_bytes(c.encoded(task))
        return task

    def test_image_dispatcher_draft_asks_only_for_the_reading(self):
        task = self.dispatcher_task()
        draft = tool.draft_inputs(self.root, 'task.json', 'draft')
        self.assertEqual((draft['choices']['visual'], draft['choices']['validation']), (None, None))
        self.assertEqual([x['field'] for x in draft['unresolved']], ['reading.reading_key'])
        self.assertEqual(tool.inspect_inputs(self.root, 'task.json')['required_choices'], ['reading'])
        self.assertEqual(adapters.build_visual(None, task, InputEvidence(self.root), self.root), (None, {}))
        self.assertEqual(adapters.build_validation(None, task, InputEvidence(self.root), self.root), (None, {}))


    def test_prepared_dispatcher_task_continues_with_draft_execution_and_execute(self):
        inputs = {'production-task': {'path': 'built/production-task.json', 'sha256': '0' * 64},
                  'request-validation': {'path': 'built/request-validation.json', 'sha256': '0' * 64}}
        usage = {}
        for route, features in (('generation', []), ('state-series', []), ('generation', ['state-series']), ('upscale', [])):
            task = {'route': route, 'features': features, 'execution': 'dispatcher'}
            actions = adapters.next_actions(inputs, task, self.root)
            self.assertEqual([action['operation'] for action in actions[-3:]], ['prepare', 'draft-execution', 'execute'])
            for action in actions[-3:]:
                self.assertEqual(action['script'], 'scripts/production_workflow.py')
                if action['operation'] not in usage:
                    usage[action['operation']] = subprocess.run(
                        [sys.executable, str(tool.ROOT / action['script']), action['operation'], '--help'],
                        capture_output=True, text=True, encoding="utf-8", check=True).stdout
                for name in [*action['args'], *action.get('required_args', [])]:
                    self.assertIn('--' + name + ' ', usage[action['operation']], (action['operation'], name))

    def test_upscale_dispatcher_needs_its_validation_choice(self):
        self.dispatcher_task(route='upscale')
        self.assertEqual(tool.inspect_inputs(self.root, 'task.json')['required_choices'], ['reading', 'validation'])

    def prepared_source(self):
        import work_ledger
        self.task['task_id'] = work_ledger.begin(self.root, 'Synthetic saved-input test', ['inspect inputs'])['task_id']
        import production_fixtures
        production_fixtures.task(self.root, self.task)
        (self.root / 'task.json').write_bytes(c.encoded(self.task))
        import production_workflow
        return production_workflow.prepare(self.root, 'task.json')['run']

    def test_saved_reading_is_copied_with_provenance_not_reissued(self):
        run = self.prepared_source()
        before = self.ledger.read_bytes()
        result = tool.draft_inputs(self.root, None, 'saved-draft', from_run=run)
        saved = result['derived_from']['source_run']
        self.assertEqual(saved['run'], run)
        self.assertEqual(result['choices']['reading']['reading_key'], saved['route_reading']['reading_key'])
        self.assertEqual(result['choices']['reading']['applied'], saved['route_reading']['applied'])
        self.assertTrue(saved['assessment_required'])
        self.assertEqual(before, self.ledger.read_bytes())

    def test_changed_source_is_reported_before_reusing_applications(self):
        run = self.prepared_source()
        (self.root / 'delivery.txt').write_text('Changed synthetic delivery for a separate assessment.', encoding='utf-8')
        before = self.files()
        result = tool.inspect_inputs(self.root, from_run=run)
        fresh = result['source_run']['freshness']
        self.assertFalse(fresh['current'])
        self.assertTrue(any(item['code'] == 'SOURCE_CHANGED' and item['file'] == 'delivery.txt' for item in fresh['diagnostics']), fresh)
        self.assertEqual(before, self.files())

    def test_edited_saved_draft_builds_without_reusing_authority(self):
        run = self.prepared_source()
        result = tool.draft_inputs(self.root, None, 'saved-draft', from_run=run)
        document = c.load(self.root / result['choices_file'])
        document['visual'] = self.choices['visual']
        document['validation'] = self.choices['validation']
        (self.root / result['choices_file']).write_bytes(c.encoded(document))
        import production_workflow
        before = copy.deepcopy(production_workflow.load_run(self.root, run)[3])
        built = tool.build_inputs(self.root, None, result['choices_file'], 'built', from_run=run)
        self.assertTrue(built['ok'])
        self.assertFalse(built['execution_ready'])
        self.assertEqual(before, production_workflow.load_run(self.root, run)[3])

    def test_saved_run_supplies_task_and_exact_delivery_without_original_files(self):
        run = self.prepared_source()
        delivery = (self.root / self.task['delivery']['path']).read_bytes()
        (self.root / 'task.json').unlink()
        (self.root / self.task['delivery']['path']).write_text('Later unrelated edit.', encoding='utf-8')
        draft = tool.draft_inputs(self.root, None, 'saved-draft', from_run=run)
        built = tool.build_inputs(self.root, None, draft['choices_file'], 'built', from_run=run)
        task = c.load(self.root / built['inputs']['production-task']['path'])
        self.assertEqual((self.root / task['delivery']['path']).read_bytes(), delivery)
        self.assertEqual(task['criteria'], self.task['criteria'])
        self.assertEqual(task['authority'], self.task['authority'])
        self.assertFalse(built['execution_ready'])

    def external_choice(self, *, with_reference=False):
        import production_fixtures
        from reading_fixtures import fixture_reading
        run = self.prepared_source()
        source = copy.deepcopy(self.task)
        plan_path = production_fixtures.external_image_input(self.root, source, count=1)
        plan = c.load(self.root / plan_path)
        plan['model']['evidence'].pop('sha256')
        request = {'controls': {'quality': 'fine', 'seed': 37}, 'palette': ['amber', 'slate']}
        if with_reference:
            from PIL import Image
            Image.new('RGB', (12, 8), (34, 56, 78)).save(self.root / 'sample.png')
            plan['references'] = [{'id': 'surface-sample', 'role': 'surface finish', 'file': 'sample.png',
                'use_for': ['surface finish'], 'do_not_transfer': ['composition']}]
            evidence = copy.deepcopy(plan['model']['evidence'])
            plan['external_request']['reference_fields'] = [
                {'reference': 'surface-sample', 'field': ['media', 0], 'value': 'synthetic-media-token',
                 'evidence': evidence}]
            request['media'] = [None]
        (self.root / plan['external_request']['file']).write_bytes(c.encoded(request))
        (self.root / plan_path).write_bytes(c.encoded(plan))
        draft = tool.draft_inputs(self.root, None, 'external-draft', from_run=run)
        choices = c.load(self.root / draft['choices_file'])
        record = fixture_reading(route='generation', features=['unlisted-interface'], studio=self.root,
                                 ledger=self.ledger)
        choices['reading'] = {key: record[key] for key in ('reading_key', 'applied', 'resource_applied')}
        choices['reading']['snapshot_id'] = None
        choices['task_changes'] = {'route': 'generation', 'features': ['unlisted-interface']}
        choices['external'] = {'image_input': plan_path}
        (self.root / draft['choices_file']).write_bytes(c.encoded(choices))
        return run, draft, plan_path, plan

    def test_external_promotion_materializes_input_without_changing_sources_or_grants(self):
        import production_workflow as workflow
        delivery = 'Synthetic line one.\r\nReference note: caf\u00e9.\r\n'.encode('utf-8')
        (self.root / self.task['delivery']['path']).write_bytes(delivery)
        run, draft, plan_path, plan = self.external_choice(with_reference=True)
        source_plan = (self.root / plan_path).read_bytes()
        source_request = (self.root / plan['external_request']['file']).read_bytes()
        original_rows = copy.deepcopy(workflow.load_run(self.root, run)[3])
        built = tool.build_inputs(self.root, None, draft['choices_file'], 'external-built', from_run=run)
        task = c.load(self.root / built['inputs']['production-task']['path'])
        request = c.load(self.root / built['inputs']['external-request']['path'])
        self.assertEqual(request['prompt'].encode('utf-8'), delivery)
        self.assertEqual((self.root / task['delivery']['path']).read_bytes(), delivery)
        self.assertEqual(request['model'], plan['model']['target']['model_identifier'])
        self.assertEqual(request['count'], 1)
        self.assertEqual(request['controls'], {'quality': 'fine', 'seed': 37})
        self.assertEqual(request['palette'], ['amber', 'slate'])
        self.assertEqual(request['media'], ['synthetic-media-token'])
        self.assertEqual(task['criteria'], self.task['criteria'])
        self.assertEqual(task['authority'], self.task['authority'])
        self.assertEqual((self.root / plan_path).read_bytes(), source_plan)
        self.assertEqual((self.root / plan['external_request']['file']).read_bytes(), source_request)
        self.assertEqual(workflow.load_run(self.root, run)[3], original_rows)
        import image_input
        binding = image_input.validate(c.load(self.root / task['image_input']), self.root)
        self.assertEqual(binding['references'][0]['sha256'], c.sha256_file(self.root / 'sample.png'))
        self.assertEqual(binding['references'][0]['do_not_transfer'], ['composition'])
        self.assertEqual(built['external_input']['request'], request)
        self.assertEqual(built['request_state'], 'materialized')
        self.assertFalse(built['execution_ready'])
        prepared = workflow.prepare(self.root, built['inputs']['production-task']['path'])
        rows = workflow.load_run(self.root, prepared['run'])[3]
        self.assertFalse(any(row['event'] in {'authorization', 'handoff', 'external-claim'} for row in rows))

    def test_external_builder_checks_existing_evidence_hashes(self):
        run, draft, plan_path, plan = self.external_choice()
        plan['model']['evidence']['sha256'] = 'f' * 64
        (self.root / plan_path).write_bytes(c.encoded(plan))
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            tool.build_inputs(self.root, None, draft['choices_file'], 'external-built', from_run=run)
        self.assertFalse((self.root / 'external-built').exists())

    def test_external_tag_input_keeps_required_dictionary_evidence(self):
        from model_prompt_input_fixtures import prompt_input
        run, draft, plan_path, plan = self.external_choice()
        plan['model']['prompt_input'] = prompt_input('tag-based', vocabularies=('synthetic-tags',))
        plan['model']['prompt_dialect'] = 'synthetic-tags'
        (self.root / plan_path).write_bytes(c.encoded(plan))
        with self.assertRaisesRegex(ValueError, 'vocabulary_record'):
            tool.build_inputs(self.root, None, draft['choices_file'], 'external-built', from_run=run)
        self.assertFalse((self.root / 'external-built').exists())

    def test_cli_help_documents_no_side_effect_build(self):
        run = subprocess.run([sys.executable, str(tool.ROOT / 'scripts/production_workflow.py'),
                              'build-inputs', '--help'], capture_output=True, text=True, encoding='utf-8', check=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('--choices', run.stdout)
        self.assertIn('--out-dir', run.stdout)

    def test_cli_build_uses_current_authored_applications(self):
        run = subprocess.run([sys.executable, str(tool.ROOT / 'scripts/production_workflow.py'),
                              'build-inputs', '--root', str(self.root), '--task', 'task.json',
                              '--choices', 'choices.json', '--out-dir', 'cli-built'],
                             capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout)['state'], 'built')
        actual = c.load(self.root / 'cli-built/route-reading.json')
        self.assertEqual(actual['applied'], self.choices['reading']['applied'])


class AuthoringRecoveryTests(unittest.TestCase):
    """A new session discovers committed local work for the current ledger task."""

    save_choices = InputToolsTests.save_choices

    def setUp(self):
        InputToolsTests.setUp(self)
        import work_ledger
        self.work = work_ledger.begin(self.root, 'Continue the synthetic authored inputs.', ['Inspect the saved inputs.'])
        self.task['task_id'] = self.work['task_id']
        (self.root / 'task.json').write_bytes(c.encoded(self.task))

    def inspect(self):
        with patch('catalog_retrieval.runtime.load_pack_catalog', side_effect=AssertionError('catalog read')):
            return tool.inspect_inputs(self.root)

    def test_saved_choices_are_current_read_only_and_scoped_to_the_open_task(self):
        import work_ledger
        import session_entry_points
        result = tool.draft_inputs(self.root, 'task.json', 'draft')
        path = self.root / result['choices_file']
        choices = c.load(path)
        choices['reading'] = copy.deepcopy(self.choices['reading'])
        path.write_bytes(c.encoded(choices))
        before = path.read_bytes()
        current = self.inspect()
        self.assertEqual(current['inputs'][0]['choices'], 'draft/choices.json')
        self.assertEqual(current['inputs'][0]['unresolved'], [])
        self.assertEqual(path.read_bytes(), before)
        with patch('catalog_retrieval.runtime.load_pack_catalog', side_effect=AssertionError('catalog read')):
            lines = session_entry_points.authoring_lines(self.root)
        self.assertIn(str(path), '\n'.join(lines))
        work_ledger.suspend(self.root, reason='Synthetic task switch.')
        work_ledger.begin(self.root, 'A different synthetic task.', ['Inspect its own inputs.'])
        self.assertEqual(self.inspect()['inputs'], [])
        self.assertEqual(path.read_bytes(), before)

    def test_published_build_is_found_when_its_caller_did_not_receive_the_result(self):
        original = tool._publish
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError('Synthetic interruption after directory publication.')
        with patch.object(tool, '_publish', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'after directory publication'):
                tool.build_inputs(self.root, 'task.json', 'choices.json', 'built')
        before = (self.root / 'built/production-task.json').read_bytes()
        current = self.inspect()
        built = current['inputs'][0]
        self.assertEqual((built['state'], built['task'], built['report']),
                         ('built', 'built/production-task.json', 'built/input-report.json'))
        self.assertIn('--task', built['next_actions'][0]['argv'])
        self.assertEqual((self.root / 'built/production-task.json').read_bytes(), before)

    def test_partial_reading_is_discovered_in_a_fresh_process_without_issuing_a_key(self):
        class InterruptedStream(io.StringIO):
            def write(self, value):
                if value.startswith('--- '):
                    raise OSError('Synthetic interruption before page delivery.')
                return super().write(value)
        before = self.ledger.read_bytes()
        with self.assertRaisesRegex(OSError, 'before page delivery'):
            reading.read_page(route='development', studio=self.root, ledger=self.ledger,
                              page_bytes=128, stream=InterruptedStream())
        program = ('import json,sys;from pathlib import Path;from unittest.mock import patch;'
                   'import production_inputs as p;'
                   '\nwith patch("catalog_retrieval.runtime.load_pack_catalog",side_effect=AssertionError("catalog read")):'
                   '\n print(json.dumps(p.inspect_inputs(Path(sys.argv[1]))))')
        run = subprocess.run([sys.executable, '-c', program, str(self.root)],
            env={**os.environ, 'PYTHONPATH': str(tool.ROOT / 'scripts')},
            capture_output=True, text=True, encoding='utf-8', check=False)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        state = json.loads(run.stdout)['readings'][0]
        self.assertEqual((state['state'], state['delivered_bytes']), ('partial', 0))
        self.assertGreater(state['remaining_bytes'], 0)
        self.assertIn(state['cursor'], state['actions']['continue']['argv'])
        self.assertEqual(self.ledger.read_bytes(), before)
        resumed = reading.read_page(cursor=state['cursor'], studio=self.root, ledger=self.ledger,
                                    page_bytes=128, stream=io.StringIO())
        self.assertEqual(resumed['snapshot'], state['snapshot'])
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_completed_reading_reuses_its_saved_application_record(self):
        page = reading.read_page(route='development', studio=self.root, ledger=self.ledger,
                                 page_bytes=10_000_000, stream=io.StringIO())
        path = reading.write_draft(page['issued'], self.ledger, studio=self.root, snapshot=page['snapshot'])
        before = self.ledger.read_bytes()
        report = self.inspect()['readings'][0]
        self.assertEqual((report['state'], report['records']), ('recorded', [str(path)]))
        self.assertEqual(report['next_actions'], [])
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_check_history_remains_a_saved_diagnostic(self):
        import uuid
        identifier = str(uuid.uuid4())
        folder = self.root / 'logs/operations/2000-01-01' / identifier
        c.atomic(folder / 'operation.json', c.encoded({'operation_id': identifier,
            'command': 'production_workflow.py', 'context': {}, 'created_at': '2000-01-01T00:00:00Z',
            'arguments': {'command': 'check', 'task': 'task.json'}}))
        c.atomic(folder / 'events.jsonl', c.encoded({'event': 'completed', 'exit_code': 1, 'complete': True}))
        saved = self.inspect()['last_check']
        self.assertEqual((saved['task'], saved['exit_code'], saved['freshness']),
                         ('task.json', 1, 'not-rechecked'))
        self.assertNotIn('execution_ready', saved)

    def test_complete_choices_emit_build_and_prepare_with_the_saved_runtime(self):
        runtime = {'state-file': str(self.root / 'runtime/state.json'),
                   'cache-dir': str(self.root / 'runtime/cache'),
                   'managed-root': str(self.root / 'runtime/managed'), 'pack-root': []}
        draft = tool.draft_inputs(self.root, 'task.json', 'draft', runtime_arguments=runtime)
        (self.root / draft['choices_file']).write_bytes(c.encoded(self.choices))
        action = self.inspect()['next_actions'][0]
        self.assertEqual(action['command'], 'build-inputs')
        for key in ('state-file', 'cache-dir', 'managed-root'):
            self.assertEqual(action['argv'][action['argv'].index('--' + key) + 1], runtime[key])
        run = subprocess.run(action['argv'], env={**os.environ, 'CPB_HOME': str(self.root / 'runtime/home')},
                             capture_output=True, text=True, encoding='utf-8', check=False)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        state = self.inspect()
        self.assertTrue(state['inputs'][0]['assembled_task'].endswith('/production-task.json'))
        prepare = state['next_actions'][0]
        self.assertEqual(prepare['command'], 'prepare')
        for key in ('state-file', 'cache-dir', 'managed-root'):
            self.assertEqual(prepare['argv'][prepare['argv'].index('--' + key) + 1], runtime[key])

    def test_unpublished_attempt_accepts_corrected_choices_and_preserves_existing_outputs(self):
        incomplete = self.root / 'incomplete.json'
        incomplete.write_bytes(c.encoded(tool.draft_choices(self.task)))
        first = tool.build_inputs(self.root, 'task.json', incomplete.name, 'built')
        self.assertFalse(first['ok'])
        built = tool.build_inputs(self.root, 'task.json', 'choices.json', 'built')
        self.assertTrue(built['ok'])
        self.assertEqual(self.inspect()['inputs'][0]['choices'], 'choices.json')
        (self.root / 'prior').mkdir()
        marker = self.root / 'prior/marker.txt'
        marker.write_text('Existing local output.', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            tool.draft_inputs(self.root, 'task.json', 'prior')
        self.assertEqual(marker.read_text(encoding='utf-8'), 'Existing local output.')
        self.assertNotIn('prior', [row['directory'] for row in self.inspect()['inputs']])

    def test_reading_before_any_page_has_an_exact_restart_action(self):
        before = self.ledger.read_bytes()
        atomic = c.atomic
        def interrupted(path, *args, **kwargs):
            if Path(path).name == 'snapshot.json':
                raise OSError('Synthetic interruption before snapshot publication.')
            return atomic(path, *args, **kwargs)
        with patch.object(c, 'atomic', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'before snapshot publication'):
                reading.read_page(route='development', studio=self.root, ledger=self.ledger,
                                  page_bytes=128, stream=io.StringIO())
        with patch.object(c, 'object_store', side_effect=OSError('Synthetic interruption before page receipt.')):
            with self.assertRaisesRegex(OSError, 'before page receipt'):
                reading.read_page(route='development', studio=self.root, ledger=self.ledger,
                                  page_bytes=128, stream=io.StringIO())
        report = self.inspect()
        self.assertEqual(len(report['readings']), 2)
        for saved in report['readings']:
            self.assertEqual(saved['state'], 'unpublished')
            self.assertNotIn('cursor', saved)
            self.assertIn('development', saved['actions']['restart']['argv'])
            self.assertNotIn('--continue', saved['actions']['restart']['argv'])
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_reading_actions_follow_the_explicit_task_features(self):
        tool.draft_inputs(self.root, 'task.json', 'draft')
        selected = reading.read_page(route='development', studio=self.root, ledger=self.ledger,
                                      page_bytes=128, stream=io.StringIO())
        other = reading.read_page(route='development', features=['studio'], studio=self.root,
                                 ledger=self.ledger, page_bytes=128, stream=io.StringIO())
        state = self.inspect()
        current = [row for row in state['readings'] if row['current']]
        self.assertEqual([row['snapshot'] for row in current], [selected['snapshot']])
        historical = next(row for row in state['readings'] if row['snapshot'] == other['snapshot'])
        self.assertEqual(historical['applicability'], 'historical')
        self.assertNotIn(other['cursor'], json.dumps(state['next_actions']))

    def test_status_contract_and_source_free_inspection_accept_saved_authoring(self):
        import production_execution
        from state_protocol import validate_against_schema
        tool.draft_inputs(self.root, 'task.json', 'draft')
        schema = c.load(tool.ROOT / 'schemas/authoring/production-status.schema.json')
        current = production_execution._current_task(self.root)
        self.assertEqual(validate_against_schema(current, {'$ref': '#/$defs/current_task', '$defs': schema['$defs']}), [])
        run = subprocess.run([sys.executable, str(tool.ROOT / 'scripts/production_workflow.py'),
                              'inspect-inputs', '--root', str(self.root)],
                             env={**os.environ, 'CPB_HOME': str(self.root / 'runtime/home')},
                             capture_output=True, text=True, encoding='utf-8', check=False)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout)['task_id'], self.work['task_id'])

    def test_unpublished_draft_resumes_from_its_saved_source_without_inventing_choices(self):
        before = self.ledger.read_bytes()
        with patch.object(tool, '_publish', side_effect=OSError('Synthetic interruption before draft publication.')):
            with self.assertRaisesRegex(OSError, 'before draft publication'):
                tool.draft_inputs(self.root, 'task.json', 'draft')
        state = self.inspect()
        self.assertFalse((self.root / 'draft').exists())
        action = state['next_actions'][0]
        self.assertEqual(action['command'], 'draft-inputs')
        self.assertEqual(action['argv'][action['argv'].index('--task') + 1], 'task.json')
        self.assertEqual(action['argv'][action['argv'].index('--out-dir') + 1], 'draft')
        restored = tool.draft_inputs(self.root, 'task.json', 'draft')
        self.assertIsNone(c.load(self.root / restored['choices_file'])['reading']['reading_key'])
        self.assertEqual(self.ledger.read_bytes(), before)
        incomplete = self.root / 'incomplete.json'
        incomplete.write_bytes(c.encoded(tool.draft_choices(self.task)))
        tool.build_inputs(self.root, 'task.json', incomplete.name, 'built')
        incomplete.unlink()
        missing = next(row for row in self.inspect()['inputs'] if row['kind'] == 'build-inputs')
        self.assertEqual(missing['unresolved'], [{'field': 'choices', 'code': 'authored-input-missing',
                                                 'path': 'incomplete.json'}])
        self.assertEqual(missing['next_actions'], [])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
