"""Exercise stage selection and fresh continuation through the public input CLI."""
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

import execution_contract as c
import production_case_fixtures as cases
import production_fixtures as fixtures
import production_inputs as inputs
import production_operations as workflow
import production_reading_scope as reading_scope
import production_report_view as views
import route_reading
import studio_workspace as studio
import work_ledger


class StageCliTests(unittest.TestCase):
    def setUp(self):
        from catalog_retrieval import runtime
        self.temporary = tempfile.TemporaryDirectory(prefix='cpb-stage-inputs-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.enterContext(fixtures.scratch_home(self.base / 'home'))
        self.enterContext(runtime.using_pack_runtime(None))
        self.root = studio.init(self.base / 'studio', 'stage-inputs', 'Synthetic stage continuation')
        self.work = work_ledger.begin(self.root, 'Compose a synthetic local description.', ['Compose'])
        self.request = fixtures.current_request(self.root, 'Compose a synthetic scene of an empty workshop.')

    def command(self, name, *arguments):
        argv = [sys.executable, str(inputs.ROOT / 'scripts/production_workflow.py'), name,
                '--root', str(self.root), *arguments, '--view', 'full']
        return self.follow(argv)

    def follow(self, argv):
        completed = subprocess.run(argv, cwd=self.root, env=dict(os.environ), capture_output=True,
                                   text=True, encoding='utf-8', timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def check_choices(self, path):
        result = subprocess.run([sys.executable, str(inputs.ROOT / 'scripts/production_workflow.py'),
            'check', '--root', str(self.root), '--choices', path], cwd=self.root,
            env=dict(os.environ), capture_output=True, text=True, encoding='utf-8', timeout=60)
        return result.returncode, json.loads(result.stdout)

    def draft(self, directory='work/draft', *, execution='authored'):
        return self.command('draft-inputs', '--route', 'development' if execution == 'authored' else 'generation',
            '--artifact', 'text' if execution == 'authored' else 'image', '--execution', execution,
            '--operation', 'compose', '--request-file', self.request, '--focus', 'supporting-setting',
            '--out-dir', directory)

    def choose(self, path, stage):
        return self.command('stage-inputs', '--choices', path, '--stage', stage)

    def read(self, path):
        result = self.follow([sys.executable, str(inputs.ROOT / 'scripts/execution_routes.py'),
            'read', '--root', str(self.root), '--choices', path, '--page-bytes', '1000000'])
        self.assertEqual(result['body'], [])
        self.assertIsNone(result['reading'])
        self.assertEqual(result['progress']['reused_bytes'], 0)
        while result['reading'] is None:
            action = result['actions'].get('continue') or result['actions']['all']
            result = self.follow(action['argv'])
        return result

    def store_key(self, path, key):
        choices = c.load(self.root / path)
        choices['reading']['reading_key'] = key
        (self.root / path).write_bytes(c.encoded(choices))

    def sources(self, path):
        folder = self.root / Path(path).parent
        return {file.relative_to(folder).as_posix(): file.read_bytes()
                for file in folder.rglob('*') if file.is_file() and file != self.root / path}

    def test_new_text_and_image_drafts_start_with_definition(self):
        for execution in ('authored', 'external'):
            with self.subTest(execution=execution):
                drafted = self.draft('work/' + execution, execution=execution)
                choices = c.load(self.root / drafted['choices_file'])
                self.assertEqual(choices['authoring_stage'], 'definition')
                self.assertEqual(drafted['authoring_stage']['stage'], 'definition')
                self.assertIsNone(choices['reading']['reading_key'])
                self.assertFalse(drafted['external_effect'])
                action = next(row for row in drafted['next_actions'] if row.get('operation') == 'read')
                page = self.follow(action['argv'])
                self.assertEqual(page['mode'], 'all')
                self.assertTrue(page['body'])
                self.assertLessEqual(sum(len(row['text'].encode('utf-8')) for row in page['body']),
                                     route_reading.DEFAULT_PAGE_BYTES)
                self.assertEqual(page['metadata']['authoring_scope']['stage'], 'definition')

    def test_inspection_finishes_the_required_scope_after_an_explicit_section(self):
        drafted = self.draft()
        path = drafted['choices_file']
        original = self.sources(path)
        indexed = self.follow([sys.executable, str(inputs.ROOT / 'scripts/execution_routes.py'),
            'read', '--root', str(self.root), '--choices', path, '--page-bytes', '1000000'])
        self.assertEqual(indexed['mode'], 'index')
        section = self.follow(indexed['actions']['next']['argv'])
        self.assertEqual(section['mode'], 'section')
        self.assertIsNone(section['actions']['continue'])
        self.assertGreater(section['progress']['remaining_bytes'], 0)
        inspected = self.command('inspect-inputs', '--choices', path)
        retained = next(row for row in inspected['readings'] if row['snapshot'] == indexed['snapshot'])
        completed = self.follow(retained['next_actions'][0]['argv'])
        self.assertEqual(completed['mode'], 'all')
        self.assertIsNotNone(completed['reading'])
        self.assertEqual(completed['progress']['remaining_bytes'], 0)
        delivered = sum(len(row['text'].encode('utf-8'))
                        for result in (section, completed) for row in result['body'])
        self.assertEqual(delivered, indexed['progress']['required_bytes'])
        record = c.load(self.root / completed['reading']['record'])
        route_reading.validate_record_content(record)
        self.assertEqual(self.sources(path), original)

    def test_stage_transitions_keep_sources_and_only_clear_a_changed_stage_key(self):
        drafted = self.draft()
        path = drafted['choices_file']
        reading = self.read(path)
        key = reading['reading']['key']
        original_sources = self.sources(path)
        original = c.load(self.root / path)
        for stage in ('definition', 'depiction', 'rendition', 'prepare'):
            with self.subTest(stage=stage):
                self.store_key(path, key)
                previous = c.load(self.root / path)
                report = self.choose(path, stage)
                changed = c.load(self.root / path)
                expected = copy.deepcopy(previous)
                if previous['authoring_stage'] != stage:
                    expected.update(authoring_stage=stage, reading={'reading_key': None})
                self.assertEqual(changed, expected)
                self.assertEqual(report['authoring_stage']['stage'], stage)
                self.assertEqual(self.sources(path), original_sources)
                self.assertEqual(changed['authoring'], original['authoring'])
                self.store_key(path, key)
                before = (self.root / path).read_bytes()
                self.choose(path, stage)
                self.assertEqual((self.root / path).read_bytes(), before)

    def test_fresh_inspection_reacquires_the_current_stage_without_prior_knowledge(self):
        path = self.draft()['choices_file']
        first = self.read(path)
        self.store_key(path, first['reading']['key'])
        self.choose(path, 'depiction')
        before = (self.root / path).read_bytes(), self.sources(path)
        report = self.command('inspect-inputs', '--choices', path)
        self.assertEqual(report['authoring_stage']['stage'], 'depiction')
        self.assertEqual(report['context']['input']['authoring_stage']['stage'], 'depiction')
        action = report['fresh_context_action']
        self.assertIn('--choices', action['argv'])
        self.assertNotIn('--known-reading', action['argv'])
        self.assertNotIn('--restart', action['argv'])
        fresh = self.follow(action['argv'])
        self.assertEqual(fresh['metadata']['authoring_scope']['stage'], 'depiction')
        self.assertEqual(fresh['progress']['reused_bytes'], 0)
        self.assertGreater(fresh['remaining_bytes'], 0)
        self.assertEqual((self.root / path).read_bytes(), before[0])
        self.assertEqual(self.sources(path), before[1])

    def test_saved_scope_without_choices_restarts_with_bounded_complete_delivery(self):
        path = self.draft()['choices_file']
        scope, task = reading_scope.from_choices(self.root, path)
        self.root = studio.init(self.base / 'scope-only-studio', 'saved-scope', 'Synthetic saved scope')
        work_ledger.begin(self.root, 'Resume the saved reading scope.', ['Read'])
        first = route_reading.read_page(route=task['route'], features=task['features'],
            operation=reading_scope.operation(scope['stage'], task['execution']),
            execution=task['execution'], authoring_scope=scope, studio=self.root,
            ledger=self.root / 'work/reads.jsonl', stream=io.StringIO(), publish_record=True)
        inspected = self.command('inspect-inputs')
        retained = next(row for row in inspected['readings'] if row['snapshot'] == first['snapshot'])
        self.assertIsNone(retained['choices'])
        action = retained['fresh_context_action']
        self.assertIn('--restart', action['argv'])
        self.assertIn('--all', action['argv'])
        self.assertNotIn('--known-reading', action['argv'])
        fresh = self.follow(action['argv'])
        self.assertNotEqual(fresh['snapshot'], first['snapshot'])
        self.assertEqual(fresh['mode'], 'all')
        self.assertEqual(fresh['metadata']['authoring_scope'], scope)
        delivered = 0
        while True:
            self.assertEqual(fresh['progress']['reused_bytes'], 0)
            size = sum(len(row['text'].encode('utf-8')) for row in fresh['body'])
            self.assertGreater(size, 0)
            self.assertLessEqual(size, route_reading.DEFAULT_PAGE_BYTES)
            delivered += size
            if fresh['reading'] is not None:
                break
            self.assertIsNotNone(fresh['actions']['continue'])
            fresh = self.follow(fresh['actions']['continue']['argv'])
        self.assertEqual(delivered, fresh['progress']['required_bytes'])
        self.assertEqual(fresh['progress']['remaining_bytes'], 0)
        route_reading.validate_record_content(c.load(self.root / fresh['reading']['record']))

    def test_early_check_returns_incomplete_content_to_its_current_stage(self):
        path = self.draft()['choices_file']
        reading = self.read(path)
        self.store_key(path, reading['reading']['key'])
        original = (self.root / path).read_bytes(), self.sources(path)
        status, checked = self.check_choices(path)
        self.assertNotEqual(status, 0)
        self.assertFalse(checked['publishable'])
        self.assertFalse(checked['formal_run_created'])
        self.assertTrue(any(row.get('field') == 'authoring.delivery.content'
                            for row in checked['diagnostics']))
        self.assertTrue(any(row.get('code') == 'TARGET_GUIDANCE_REQUIRED'
                            for row in checked['diagnostics']))
        self.assertEqual(checked['next_action'].get('command'), 'inspect-inputs')
        resumed = self.follow(checked['next_action']['argv'])
        self.assertEqual(resumed['authoring_stage']['stage'], 'definition')
        self.assertFalse(resumed['authoring_stage']['final_inputs_ready'])
        self.assertEqual((self.root / path).read_bytes(), original[0])
        self.assertEqual(self.sources(path), original[1])

    def test_check_still_advances_complete_content_to_final_scope(self):
        self.direct_task()
        drafted = self.command('draft-inputs', '--task', 'task.json', '--operation', 'compose',
            '--request-file', self.request, '--focus', 'supporting-setting', '--out-dir', 'work/ready')
        path = drafted['choices_file']
        reading = self.read(path)
        self.store_key(path, reading['reading']['key'])
        status, checked = self.check_choices(path)
        self.assertNotEqual(status, 0)
        self.assertFalse(checked['publishable'])
        self.assertFalse(checked['formal_run_created'])
        self.assertEqual(checked['next_action']['stage'], 'prepare')
        resumed = self.follow(checked['next_action']['argv'])
        self.assertEqual(resumed['authoring_stage']['stage'], 'prepare')
        final = self.read(path)
        self.store_key(path, final['reading']['key'])
        status, checked = self.check_choices(path)
        self.assertEqual(status, 0, checked)
        self.assertTrue(checked['publishable'])

    def test_new_action_slice_requires_its_undelivered_contract(self):
        path = self.draft()['choices_file']
        self.choose(path, 'depiction')
        first = self.read(path)
        self.store_key(path, first['reading']['key'])
        choices = c.load(self.root / path)
        choices['authoring']['task']['direction']['action_slice'] = {
            'phase': 'A fixture shutter is midway through closing.',
            'before': 'The fixture shutter was open.', 'after': 'The fixture shutter is closed.',
            'relations': [], 'not_verified': ['No image observation is claimed.']}
        (self.root / path).write_bytes(c.encoded(choices))
        report = self.command('inspect-inputs', '--choices', path)
        self.assertIn('action-slice', report['authoring_scope']['conditions'])
        diagnostics = report['authoring_stage']['unresolved']
        missing = [row for row in diagnostics if row.get('code') == 'TARGET_GUIDANCE_REQUIRED']
        self.assertTrue(missing, diagnostics)
        action = missing[0]['next_action']
        self.assertIn(path, action['argv'])
        fresh = self.follow(action['argv'])
        self.assertIn('action-slice', fresh['metadata']['authoring_scope']['conditions'])
        current = self.read(path)
        self.store_key(path, current['reading']['key'])
        restored = self.command('inspect-inputs', '--choices', path)
        self.assertFalse(any(row.get('code') == 'TARGET_GUIDANCE_REQUIRED'
                             for row in restored['authoring_stage']['unresolved']))

    def test_summary_keeps_every_current_answer_and_locates_later_stage_omissions(self):
        current = [{'field': 'definition.' + str(number), 'code': 'CURRENT_ANSWER',
                    'message': 'Answer this actual definition field.'} for number in range(12)]
        later = [{'field': 'prepare.' + str(number), 'code': 'LATER_INPUT',
                  'message': 'Resolve this final input when preparing.'} for number in range(35)]
        stage = {'stage': 'definition', 'purpose': 'Establish the fixture definition.',
            'structural_ready': False, 'final_inputs_ready': False, 'unresolved': current, 'pending': later,
            'meaning': 'No artistic completion is inferred.'}
        row = {'state': 'choices', 'kind': 'draft-inputs', 'directory': 'work/draft',
            'choices': 'work/draft/choices.json', 'current': True, 'unresolved': current + later,
            'authoring_stage': stage, 'next_actions': []}
        report = {'state': 'authoring-state', 'task_id': self.work['task_id'], 'inputs': [row],
            'authoring_stage': stage, 'context': {'work': {}, 'input': row}, 'next_actions': []}
        result = views.authoring_state(self.root, report)
        self.assertEqual({row['field'] for row in result['diagnostics']}, {row['field'] for row in current})
        for displayed in (result['authoring_stage'], result['inputs'][0]['authoring_stage'],
                          result['context']['input']['authoring_stage']):
            self.assertEqual(displayed['pending_summary']['total'], len(later))
            self.assertIn('/authoring_stage/pending', displayed['pending_summary']['full_report'])
            self.assertEqual(len(displayed['diagnostic_ids']), len(current))

    def test_registered_runtime_survives_stage_and_fresh_read_then_prepares_current_choices(self):
        from catalog_retrieval import runtime
        case = cases.create(self.base / 'model-studio', self.base / 'selected-runtime')
        self.root = case['root']
        settings = case['settings']
        arguments = {'state-file': str(settings.state_file.resolve()),
            'cache-dir': str(settings.cache_dir.resolve()),
            'managed-root': str(settings.managed_root.resolve()),
            'pack-root': [str(case['pack'].resolve())]}
        original_task = (self.root / 'task.json').read_bytes()
        saved = workflow.prepare(self.root, 'task.json')['run']
        loaded = workflow.read_run(self.root, saved)
        original_run = {path.relative_to(loaded.directory).as_posix(): path.read_bytes()
                        for path in loaded.directory.rglob('*') if path.is_file()}
        self.request = fixtures.current_request(self.root)
        flags = [word for name, value in arguments.items()
                 for item in (value if isinstance(value, list) else [value])
                 for word in ('--' + name, str(item))]
        drafted = self.command('draft-inputs', '--from-run', saved, '--operation', 'amend',
            '--request-file', self.request, '--out-dir', 'work/current', *flags)
        path = drafted['choices_file']
        runtime.configure_pack_runtime(None)
        report = self.choose(path, 'prepare')
        self.assertEqual(report['authoring_stage']['stage'], 'prepare')
        action = report['fresh_context_action']
        for name, value in arguments.items():
            self.assertEqual(action['args'][name], value)
        indexed = self.follow(action['argv'])
        self.assertEqual(indexed['metadata']['model']['id'], case['model'])
        self.assertEqual(indexed['progress']['reused_bytes'], 0)
        result = indexed
        while result['reading'] is None:
            action = result['actions'].get('continue') or result['actions']['all']
            result = self.follow(action['argv'])
        self.store_key(path, result['reading']['key'])
        inspected = self.command('inspect-inputs', '--choices', path)
        prepare = next(item for item in inspected['next_actions'] if item.get('command') == 'prepare')
        for name, value in arguments.items():
            self.assertEqual(prepare['args'][name], value)
        completed = self.follow([*prepare['argv'], '--view', 'full'])
        self.assertTrue(completed['ok'], completed)
        self.assertNotEqual(completed['run'], saved)
        self.assertEqual((self.root / 'task.json').read_bytes(), original_task)
        self.assertEqual({path.relative_to(loaded.directory).as_posix(): path.read_bytes()
                          for path in loaded.directory.rglob('*') if path.is_file()}, original_run)

    def direct_task(self):
        task = {'task_id': self.work['task_id'], 'route': 'development', 'features': [], 'sources': [],
            'delivery': {'path': 'delivery.txt', 'translation_notes': None},
            'criteria': [{'id': 'meaning', 'strength': 'hard', 'text': 'The text describes an empty workshop.'}],
            'world_views': []}
        fixtures.task(self.root, task, focus='supporting-setting')
        (self.root / 'delivery.txt').write_text('An empty workshop after the rain.\n', encoding='utf-8')
        (self.root / 'task.json').write_bytes(c.encoded(task))
        return task

    def scoped_task_reading(self, task, stage, *, conditions=(), source_formats=()):
        scope = {'stage': stage, 'composition': 'compose', 'source_formats': sorted(source_formats),
            'documents': [], 'render_operation': 'generation', 'conditions': sorted(conditions)}
        issued = route_reading.issue(task['route'], task['features'], execution=task['execution'],
            studio=self.root, stream=io.StringIO(), authoring_scope=scope)
        (self.root / task['route_reading']).write_bytes(c.encoded(route_reading.draft_record(issued)))

    def direct_prepare(self):
        result = subprocess.run([sys.executable, str(inputs.ROOT / 'scripts/production_workflow.py'),
            'prepare', '--root', str(self.root), '--task', 'task.json', '--view', 'full'],
            cwd=self.root, env=dict(os.environ), capture_output=True, text=True, encoding='utf-8', timeout=60)
        return result.returncode, json.loads(result.stdout)

    def test_public_direct_task_requires_final_scope_and_accepts_its_complete_scoped_reading(self):
        task = self.direct_task()
        for stage in ('definition', 'depiction', 'rendition'):
            with self.subTest(stage=stage):
                self.scoped_task_reading(task, stage)
                status, report = self.direct_prepare()
                self.assertNotEqual(status, 0, report)
                self.assertFalse(report['formal_run_created'])
                self.assertTrue(any(row['phase'] == 'route-reading' and row['state'] == 'failed'
                                    for row in report['checks']), report)
        self.scoped_task_reading(task, 'prepare')
        status, report = self.direct_prepare()
        self.assertEqual(status, 0, report)
        self.assertTrue(report['formal_run_created'])
        self.assertEqual(report['state'], 'finished')

    def test_public_direct_task_rederives_selected_image_requirements_from_current_sources(self):
        task = self.direct_task()
        self.scoped_task_reading(task, 'prepare')
        # A genuinely selected binary source changes the applicable knowledge;
        # the old receipt's no-image declaration cannot choose final sufficiency.
        (self.root / 'image.png').write_bytes(b'\x89PNG\r\n\x1a\nSynthetic acquired image source.')
        task['sources'].append({'id': 'selected-image', 'path': 'image.png', 'role': 'reference',
            'disposition': 'applied', 'locator': 'whole image', 'reason': 'Current selected appearance source.'})
        fixtures.bind_work_basis(self.root, task, focus='supporting-setting')
        (self.root / 'task.json').write_bytes(c.encoded(task))
        status, report = self.direct_prepare()
        self.assertNotEqual(status, 0, report)
        self.assertFalse(report['formal_run_created'])
        self.assertTrue(any(row['phase'] == 'route-reading' and row['state'] == 'failed'
                            for row in report['checks']), report)
        self.scoped_task_reading(task, 'prepare', conditions=['image-source'], source_formats=['image'])
        status, report = self.direct_prepare()
        self.assertEqual(status, 0, report)
        self.assertTrue(report['formal_run_created'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
