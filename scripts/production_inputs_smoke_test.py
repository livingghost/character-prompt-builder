#!/usr/bin/env python3
"""Exercise authored input assembly with local synthetic sources and no provider."""
from __future__ import annotations

import copy
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
from smoke_fixtures import isolate_home

isolate_home()


class InputToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task = {'task_id': 'synthetic-task', 'route': 'development', 'features': [],
                     'sources': [], 'delivery': {'path': 'delivery.txt', 'transport': 'authored-rendition',
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
        self.issued = reading.issue('development', project=self.root, ledger=self.ledger,
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
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

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
        self.assertIsNone(draft['choices']['reading']['reading_key'])
        self.assertIsNone(draft['choices']['visual'])
        self.assertIsNone(draft['choices']['validation'])
        self.assertTrue(draft['unresolved'])
        self.assertNotIn('clear', json.dumps(draft['choices']))

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
        reading.require_route_reading(record, project=self.root)
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

    def test_source_run_requires_matching_explicit_selector(self):
        self.choices['source_run'] = '01900000-0000-7000-8000-000000000001'
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
        reading.issue('development', project=self.root, ledger=self.ledger, stream=io.StringIO(), key='3' * 32)
        self.assertTrue(self.build()['ok'])

    def test_draft_report_cannot_clear_unresolved_choices(self):
        draft = tool.draft_inputs(self.root, 'task.json', 'draft')
        raw = c.load(self.root / draft['choices_file'])
        raw['unresolved'] = []
        (self.root / 'choices.json').write_bytes(c.encoded(raw))
        result = self.build()
        self.assertFalse(result['ok'])
        self.assertTrue(result['unresolved'])

    def test_complete_edited_draft_uses_same_builder(self):
        document = {'state': 'draft', 'choices': self.choices, 'unresolved': [],
                    'derived_from': {}, 'external_effect': False, 'budget_effect': 'none'}
        (self.root / 'choices.json').write_bytes(c.encoded(document))
        self.assertTrue(self.build()['ok'])

    def test_output_path_cannot_escape_project(self):
        with self.assertRaises(ValueError):
            self.build('../escaped')

    def dispatcher_task(self, transport='authored-rendition', route='development'):
        task = copy.deepcopy(self.task)
        task.update(artifact='image', execution='dispatcher', route=route)
        task['delivery']['transport'] = transport
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

    def test_bounded_context_dispatcher_needs_its_validation_choice(self):
        task = self.dispatcher_task('bounded-context')
        draft = tool.draft_inputs(self.root, 'task.json', 'draft')
        self.assertIn('validation.mode', [x['field'] for x in draft['unresolved']])
        self.choices['validation'] = None
        self.save_choices()
        self.assertIn({'field': 'validation', 'code': 'selection-required'}, self.build()['unresolved'])
        with self.assertRaisesRegex(ValueError, 'request validation choice'):
            adapters.build_validation(None, task, InputEvidence(self.root), self.root)
        self.assertFalse((self.root / 'built').exists())

    def test_builder_action_names_the_builder_for_the_task(self):
        inputs = {'production-task': {'path': 'built/production-task.json', 'sha256': '0' * 64}}
        usage = {}
        for route, features, script in (
                ('generation', [], 'scripts/build_generation_payload.py'),
                ('state-series', [], 'scripts/build_state_generation_package.py'),
                ('generation', ['state-series'], 'scripts/build_state_generation_package.py')):
            task = {'route': route, 'features': features, 'execution': 'dispatcher'}
            action = adapters.next_actions(inputs, task, self.root)[-1]
            self.assertEqual((action['operation'], action['script']), ('build-generation-payload', script))
            if script not in usage:
                usage[script] = subprocess.run([sys.executable, str(tool.ROOT / script), '--help'],
                                               capture_output=True, text=True, encoding="utf-8", check=True).stdout
            for name in action['required_args']:
                self.assertIn('--' + name + ' ', usage[script], (script, name))

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
        result = tool.draft_inputs(self.root, 'task.json', 'saved-draft', from_run=run)
        saved = result['derived_from']['source_run']
        self.assertEqual(result['choices']['source_run'], run)
        self.assertEqual(result['choices']['reading']['reading_key'], saved['route_reading']['reading_key'])
        self.assertEqual(result['choices']['reading']['applied'], saved['route_reading']['applied'])
        self.assertTrue(saved['assessment_required'])
        self.assertEqual(before, self.ledger.read_bytes())

    def test_changed_source_is_reported_before_reusing_applications(self):
        run = self.prepared_source()
        (self.root / 'delivery.txt').write_text('Changed synthetic delivery for a separate assessment.', encoding='utf-8')
        before = self.files()
        result = tool.inspect_inputs(self.root, 'task.json', from_run=run)
        fresh = result['source_run']['freshness']
        self.assertFalse(fresh['current'])
        self.assertIn('delivery.txt', [change['path'] for change in fresh['changes']])
        self.assertEqual(before, self.files())

    def test_edited_saved_draft_builds_without_reusing_authority(self):
        run = self.prepared_source()
        result = tool.draft_inputs(self.root, 'task.json', 'saved-draft', from_run=run)
        document = c.load(self.root / result['choices_file'])
        document['choices']['visual'] = self.choices['visual']
        document['choices']['validation'] = self.choices['validation']
        (self.root / result['choices_file']).write_bytes(c.encoded(document))
        import production_workflow
        before = copy.deepcopy(production_workflow.load_run(self.root, run)[3])
        built = tool.build_inputs(self.root, 'task.json', result['choices_file'], 'built', from_run=run)
        self.assertTrue(built['ok'])
        self.assertFalse(built['execution_ready'])
        self.assertEqual(before, production_workflow.load_run(self.root, run)[3])

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


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
