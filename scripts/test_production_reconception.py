"""Actual authoring operations share source acquisition, application and delivery.

Synthetic inputs check data ownership and saved continuations. They make no
claim about artistic range or whether a chosen depiction meets a human brief.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import authoring_work as core
import execution_contract as c
import production_authoring as authoring
import production_authoring_work as adapter
import production_authored
import production_case_fixtures as cases
import production_fixtures as fixtures
import production_inputs as inputs
import production_operations as workflow
from reading_fixtures import fixture_reading
import work_ledger


DEFINITION = {'body': 'A continuous curved shell with a smaller inset shell connected below its upper rim.'}


def plain_choices():
    task = authoring.seed(route='development', artifact='text', execution='authored', task_id='synthetic-work')
    choices = inputs.draft_choices(task)
    choices['authoring'] = authoring.blank(task)
    return task, choices


def source_row(ident, path, role='design'):
    return {'id': ident, 'path': path, 'role': role, 'disposition': 'applied',
            'locator': 'whole source', 'reason': 'Explicit synthetic source selection.'}


class ActualWorkProjectionTests(unittest.TestCase):
    def test_selected_requirement_reaches_current_input_with_complete_original_available(self):
        _, choices = plain_choices()
        original = {'requirement': 'The small shell stays connected.', 'comparison': 'A complete catalog display.'}
        acquired = core.acquire_source(c.encoded(original), format='json',
            origin={'kind': 'studio-source', 'source': source_row('brief', 'brief.json')})
        work = core.begin_work(operation='compose', request='Show the connection clearly.',
            sources={'brief': acquired}, applications={'connection': {'source': 'brief', 'pointer': '/requirement'}},
            requirements=['connection'], content=choices, focus='supporting-setting')
        current, files, _ = adapter.project(work['basis'], work['content'], 'editing')
        selected = next(row for row in current['authoring']['task']['sources'] if row['id'] == 'brief')
        self.assertEqual(c.decode(files[selected['path'].removeprefix('editing/')]), original['requirement'])
        self.assertEqual(c.decode(files[selected['origin']['path'].removeprefix('editing/')]), original)
        self.assertEqual(selected['origin']['sha256'], acquired['sha256'])
        self.assertNotIn('comparison', c.decode(files[selected['path'].removeprefix('editing/')]))

    def test_current_request_bytes_follow_the_one_request_owner(self):
        _, choices = plain_choices()
        work = core.begin_work(operation='compose', request='The first actual request.', content=choices,
                               focus='supporting-setting')
        basis = core.revise_basis(work['basis'], request='The changed actual request.\n実際の依頼。')
        current, files, request = adapter.project(basis, choices, 'editing')
        self.assertEqual(files[request['path'].removeprefix('editing/')], basis['request'].encode('utf-8'))
        brief = next(row for row in current['authoring']['task']['sources'] if row['role'] == 'brief')
        self.assertEqual(brief['id'], 'request:' + basis['request_sha256'])
        self.assertEqual(request['source'], brief['id'])

    def test_compose_keeps_definition_and_scoped_allowance_without_selected_method(self):
        task, choices = plain_choices()
        raw = c.encoded(DEFINITION)
        task['sources'] = [source_row('definition', 'definition.json'), source_row('method', 'method.txt'),
                           source_row('allowance', 'allowance.txt', 'approval')]
        task['sources'][0]['identity'] = {'subject_ids': ['shell'], 'selectors': ['']}
        task['criteria'] = [{'id': 'connection', 'strength': 'hard', 'text': 'The shells stay connected.', 'evidence': 'artifact'},
                            {'id': 'old-view', 'strength': 'advisory', 'text': 'Old complete view.', 'evidence': 'artifact'}]
        allowance = {'id': 'overlap', 'source': 'allowance', 'locator': 'whole text', 'author': fixtures.ACTOR,
                     'scope': {'kind': 'source', 'source': 'definition', 'sha256': c.digest(raw)},
                     'allowance': 'The shells can overlap.', 'limits': ['The connection stays intact.'],
                     'criteria': ['connection']}
        task['direction'].update(purpose='Old catalog display.', intended_effect='Old complete view.',
            basis=['definition', 'method', 'allowance'], source_allowances=[allowance],
            decisions=[{'id': 'old-display', 'basis': ['method'], 'expression': 'The complete catalog display.',
                'realization': {'method': 'catalog illustration', 'instructions': 'Old display.',
                                'capability_source': None, 'limitations': []},
                'criteria': ['old-view'], 'depends_on': [], 'deviations': []}])
        choices['authoring'] = authoring.blank(task)
        choices['authoring']['delivery']['content'] = 'The old display text.'
        choices['target'] = {'kind': 'catalog', 'model': 'old-model', 'service': 'old-service'}
        material = {'definition.json': raw, 'method.txt': b'Old display method.', 'allowance.txt': b'Explicit allowance.'}
        current, basis, _ = adapter.begin(choices, task=task, operation='compose', request='Show the connection.',
            read_source=material.__getitem__, protected_criteria={'connection'})
        current, files, _ = adapter.project(basis, current, 'editing')
        self.assertEqual(current['authoring']['task']['direction']['decisions'], [])
        self.assertEqual(current['authoring']['task']['direction']['source_allowances'], [allowance])
        self.assertEqual([row['id'] for row in current['authoring']['task']['criteria']], ['connection'])
        self.assertIsNone(current['target'])
        self.assertIsNone(current['authoring']['delivery']['content'])
        self.assertNotIn('method', {row['id'] for row in current['authoring']['task']['sources']})
        self.assertEqual(core.source_bytes(basis['sources']['method']), b'Old display method.')
        self.assertEqual(basis['baseline']['authoring']['delivery']['content'], 'The old display text.')

    def test_amend_changes_actual_delivery_and_retains_other_content(self):
        task, choices = plain_choices()
        choices['authoring']['delivery']['content'] = 'The shell tilts toward its partner.'
        choices['authoring']['task']['direction']['purpose'] = 'Keep the relationship readable.'
        current, basis, _ = adapter.begin(choices, task=task, operation='amend', request='Tilt it away.',
                                         read_source=lambda _: b'')
        changed = core.replace_text({'basis': basis, 'content': current}, '/authoring/delivery/content',
                                    'toward', 'away from')
        result = core.resolve_work(changed, complete=True)
        self.assertEqual(result['content']['authoring']['delivery']['content'], 'The shell tilts away from its partner.')
        self.assertEqual(result['content']['authoring']['task']['direction']['purpose'],
                         choices['authoring']['task']['direction']['purpose'])
        self.assertEqual(basis['baseline']['authoring']['delivery']['content'], 'The shell tilts toward its partner.')

    def test_actual_subject_owner_can_be_filled_progressively_and_removed(self):
        task, choices = plain_choices()
        choices['authoring']['documents']['production_spec'] = {'subjects': [{'id': 'shell', 'identity': None}]}
        work = core.begin_work(operation='compose', request='Describe a shell character.', content=choices)
        basis = adapter.bind_task_subjects(work['basis'], choices)
        self.assertTrue(adapter.unresolved(basis, choices, require_subject=True))
        choices['authoring']['documents']['production_spec']['subjects'][0]['identity'] = [DEFINITION['body']]
        basis = adapter.bind_task_subjects(basis, choices)
        self.assertEqual(adapter.unresolved(basis, choices, require_subject=True), [])
        selected = core.resolve_work({'basis': basis, 'content': choices}, require_subject=True)['context']
        self.assertEqual(selected['applications']['task-subject:shell']['value'], [DEFINITION['body']])
        choices['authoring']['documents']['production_spec']['subjects'] = []
        basis = adapter.bind_task_subjects(basis, choices)
        self.assertEqual(basis['subjects'], {})
        self.assertIn('task-subject:shell', basis['sources'])
        self.assertTrue(adapter.unresolved(basis, choices, require_subject=True))

    def test_published_task_local_definition_tracks_its_actual_document_after_reopening(self):
        task, choices = plain_choices()
        choices['authoring']['documents']['production_spec'] = {
            'subjects': [{'id': 'shell', 'identity': [DEFINITION['body']], 'pose': 'tilted'}]}
        work = core.begin_work(operation='compose', request='Describe the connected shell.', content=choices)
        basis = adapter.bind_task_subjects(work['basis'], choices)
        published, files, _ = adapter.project(basis, choices, 'published')
        source = next(row for row in published['authoring']['task']['sources']
                      if row['id'] == 'task-subject:shell')
        self.assertEqual(source['definition_owner'], {'document': 'production_spec', 'subject_id': 'shell'})
        self.assertEqual(source['applications'], [{'id': 'task-subject:shell', 'pointer': '/identity',
                                                   'subjects': ['shell'], 'requirement': False}])
        reopened, acquired, _ = adapter.begin(published, task=published['authoring']['task'],
            operation='amend', request='Reconsider its shell shape.',
            read_source=lambda path: files[path.removeprefix('published/')])
        changed = 'A continuous square shell with its inset shell connected beneath the upper edge.'
        reopened['authoring']['documents']['production_spec']['subjects'][0]['identity'] = [changed]
        acquired = adapter.bind_task_subjects(acquired, reopened)
        selected = core.resolve_work({'basis': acquired, 'content': reopened}, require_subject=True)['context']
        self.assertEqual(selected['applications']['task-subject:shell']['value'], [changed])
        self.assertEqual(adapter.unresolved(acquired, reopened, require_subject=True), [])
        reopened['authoring']['documents']['production_spec']['subjects'] = []
        acquired = adapter.bind_task_subjects(acquired, reopened)
        self.assertEqual(acquired['subjects'], {})
        self.assertEqual(acquired['applications'], {})
        self.assertIn('task-subject:shell', acquired['sources'])
        self.assertTrue(adapter.unresolved(acquired, reopened, require_subject=True))

    def test_composed_definition_is_an_independent_selected_source_after_publication(self):
        task, choices = plain_choices()
        choices['authoring']['documents']['production_spec'] = {
            'subjects': [{'id': 'shell', 'identity': [DEFINITION['body']]}]}
        work = core.begin_work(operation='compose', request='Describe the connected shell.', content=choices)
        basis = adapter.bind_task_subjects(work['basis'], choices)
        published, files, _ = adapter.project(basis, choices, 'published')
        composed, retained, _ = adapter.begin(published, task=published['authoring']['task'],
            operation='compose', request='Choose a new way to reveal the connection.', prior_basis=basis,
            read_source=lambda path: files[path.removeprefix('published/')])
        current, current_files, _ = adapter.project(retained, composed, 'composed')
        source = next(row for row in current['authoring']['task']['sources']
                      if row['id'] == 'task-subject:shell')
        self.assertNotIn('definition_owner', source)
        reopened, acquired, _ = adapter.begin(current, task=current['authoring']['task'], operation='amend',
            request=retained['request'], read_source=lambda path: current_files[path.removeprefix('composed/')])
        selected = core.resolve_work({'basis': acquired, 'content': reopened}, require_subject=True)['context']
        self.assertEqual(selected['applications']['task-subject:shell']['value'], [DEFINITION['body']])


class SavedAuthoringWorkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cpb-authoring-work-')
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / 'studio'
        self.root.mkdir()
        self.enterContext(fixtures.scratch_home(base / 'home'))
        self.enterContext(patch.dict(os.environ, {'CPB_READS_LEDGER': str(self.root / 'work/reads.jsonl')}))
        task_id = work_ledger.begin(self.root, 'Navigation title only.', ['Compose the text.'])['task_id']
        self.task = {'task_id': task_id, 'route': 'development', 'features': [],
            'sources': [source_row('original', 'definition.json'), source_row('method', 'method.txt')],
            'delivery': {'path': 'delivery.txt', 'translation_notes': None},
            'criteria': [{'id': 'connection', 'strength': 'hard', 'text': 'The text states the shell connection.'}],
            'world_views': []}
        self.write('definition.json', DEFINITION)
        self.write('method.txt', 'An earlier catalog display convention.')
        self.write('delivery.txt', 'A catalog description of the connected shell.\n')
        fixtures.task(self.root, self.task)
        self.write('task.json', self.task)
        self.write('request.txt', 'Describe the shell character in a catalog display.\n')

    def write(self, path, value):
        cases.write(self.root / path, value)

    def bind_definition(self, drafted):
        path = drafted['authoring_work']['basis']
        basis = c.load(self.root / path)
        basis = core.revise_basis(basis, subjects={'shell': ['original']})
        self.write(path, basis)

    def start(self):
        draft = inputs.draft_inputs(self.root, 'task.json', 'first', operation='amend', request_file='request.txt')
        self.bind_definition(draft)
        return draft

    def finish(self, drafted, text='The inset shell remains connected beneath the outer rim.\n'):
        choices = c.load(self.root / drafted['choices_file'])
        task = choices['authoring']['task']
        task['direction'].update(purpose='Make the requested shell relation readable.', intended_effect='A clear connection.')
        if not task['criteria']:
            task['criteria'] = [{'id': 'current-connection', 'strength': 'hard', 'evidence': 'artifact',
                                 'text': 'The text states the connection.'}]
        self.write(choices['authoring']['delivery']['file'], text)
        reading = fixture_reading(route=task['route'], execution=task['execution'], features=task['features'],
            studio=self.root, ledger=self.root / 'work/reads.jsonl', operation='author')
        choices['reading']['reading_key'] = reading['reading_key']
        self.write(drafted['choices_file'], choices)
        return workflow.save(self.root, drafted['choices_file'])['run']

    def source_bytes(self, loaded, ident):
        source = next(row for row in loaded.prepared['task']['sources'] if row['id'] == ident)
        item = next(row for row in loaded.prepared['dependencies'] if row['path'] == source['path'])
        return loaded.evidence.read(item['sha256'])

    def test_inspection_derives_current_definition_bytes_without_publishing_them(self):
        draft = self.start()
        choices = c.load(self.root / draft['choices_file'])
        cases.write_document(self.root, choices, 'production_spec', {
            'subjects': [{'id': 'new-shell', 'identity': [DEFINITION['body']]}]})
        self.write(draft['choices_file'], choices)
        folder = self.root / 'first'
        before = {path.relative_to(folder).as_posix(): path.read_bytes()
                  for path in folder.rglob('*') if path.is_file()}
        view = inputs.authoring_view(self.root, draft['choices_file'])
        selected = next(row for row in view['task']['sources'] if row['id'] == 'task-subject:new-shell')
        self.assertEqual(c.decode(view['captured'][selected['path']]), [DEFINITION['body']])
        self.assertFalse((self.root / selected['path']).exists())
        self.assertEqual({path.relative_to(folder).as_posix(): path.read_bytes()
                          for path in folder.rglob('*') if path.is_file()}, before)
        self.write(selected['path'], 'Different bytes at the generated content address.')
        with self.assertRaisesRegex(ValueError, 'differs from its local content address'):
            inputs.authoring_view(self.root, draft['choices_file'])

    def test_comparison_reads_live_delivery_and_definition_without_changing_sources_or_history(self):
        parent = self.finish(self.start())
        drafts = [inputs.draft_inputs(self.root, None, folder, from_run=parent,
                                      operation='amend') for folder in ('comparison-a', 'comparison-b')]
        paths = [draft['choices_file'] for draft in drafts]
        identities = ['An inset shell with three narrow hinged segments.',
                      'An inset shell with a continuous flexible rim.']
        deliveries = ['The hinged segments reach around the opening.\r\n',
                      'The flexible rim rests across the opening.\n']
        for draft, identity, delivery in zip(drafts, identities, deliveries):
            choices = c.load(self.root / draft['choices_file'])
            cases.write_document(self.root, choices, 'production_spec', {
                'subjects': [{'id': 'current-shell', 'identity': [identity]}]})
            self.write(choices['authoring']['delivery']['file'], delivery)
            self.write(draft['choices_file'], choices)

        def snapshot():
            return {path.relative_to(self.root).as_posix(): path.read_bytes()
                    for path in self.root.rglob('*') if path.is_file()}

        before = snapshot()
        report = inputs.compare_inputs(self.root, paths)
        self.assertEqual(report['state'], 'intermediate')
        for index, candidate in enumerate(report['candidates']):
            view = candidate['view']
            self.assertEqual(view['content']['authoring']['delivery']['content'], deliveries[index])
            self.assertEqual(view['content']['authoring']['documents']['production_spec']['subjects'][0]['identity'],
                             [identities[index]])
            selected = view['subjects']['current-shell'][0]
            self.assertEqual((selected['application'], selected['pointer'], selected['value']),
                             ('task-subject:current-shell', '/identity', [identities[index]]))
            self.assertNotIn('current-shell', c.decode(before[drafts[index]['authoring_work']['basis']])['subjects'])
        self.assertEqual(snapshot(), before)

        current = c.load(self.root / paths[1])
        updated_identity = 'An inset shell with two overlapping articulated panels.'
        cases.write_document(self.root, current, 'production_spec', {
            'subjects': [{'id': 'current-shell', 'identity': [updated_identity]}]})
        changed_delivery = 'The overlapping panels turn toward the ledge.\n'
        self.write(current['authoring']['delivery']['file'], changed_delivery)
        before_refresh = snapshot()
        refreshed = inputs.compare_inputs(self.root, paths)
        self.assertEqual(refreshed['candidates'][1]['view']['subjects']['current-shell'][0]['value'],
                         [updated_identity])
        self.assertEqual(refreshed['candidates'][1]['view']['content']['authoring']['delivery']['content'],
                         changed_delivery)
        self.assertNotEqual(refreshed['candidates'][1]['work_digest'], report['candidates'][1]['work_digest'])
        self.assertEqual(snapshot(), before_refresh)

    def test_comparison_reads_unfinished_work_without_completing_or_registering_it(self):
        draft = inputs.draft_inputs(self.root, None, 'unresolved-comparison', operation='compose',
                                    route='prompt-only', artifact='text', execution='authored')
        before = {path.relative_to(self.root).as_posix(): path.read_bytes()
                  for path in self.root.rglob('*') if path.is_file()}
        actual = inputs.authoring_view(self.root, draft['choices_file'], register=False)
        self.assertTrue(actual['unresolved'])
        self.assertIsNone(actual['authoring_work']['basis']['request'])
        report = inputs.compare_inputs(self.root, [draft['choices_file']])
        self.assertEqual(report['state'], 'intermediate')
        self.assertIsNone(report['candidates'][0]['view']['request'])
        self.assertEqual(report['candidates'][0]['view']['subjects'], {})
        self.assertEqual(report['candidates'][0]['view']['content'], actual['resolved_choices'])
        self.assertEqual({path.relative_to(self.root).as_posix(): path.read_bytes()
                          for path in self.root.rglob('*') if path.is_file()}, before)

    def test_cli_compares_repeated_choices_using_the_same_studio_path_boundary(self):
        first = self.start()
        second = inputs.draft_inputs(self.root, 'task.json', 'second', operation='amend',
                                      request_file='request.txt')
        self.bind_definition(second)
        self.write(first['choices']['authoring']['delivery']['file'], 'The shell opens toward the ledge.\n')
        self.write(second['choices']['authoring']['delivery']['file'], 'The shell rests beside the opening.\n')
        before = {path.relative_to(self.root).as_posix(): path.read_bytes()
                  for path in self.root.rglob('*') if path.is_file()}
        result = subprocess.run([sys.executable, str(workflow.ROOT / 'scripts/production_workflow.py'),
            'compare-inputs', '--root', str(self.root), '--choices', first['choices_file'],
            '--choices', str(self.root / second['choices_file'])], cwd=self.root, env=dict(os.environ),
            capture_output=True, text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['artifact_type'], 'authoring-work-comparison')
        self.assertEqual([candidate['label'] for candidate in report['candidates']],
                         [first['choices_file'], second['choices_file']])
        self.assertEqual([candidate['view']['content']['authoring']['delivery']['content']
                          for candidate in report['candidates']],
                         ['The shell opens toward the ledge.\n', 'The shell rests beside the opening.\n'])
        self.assertEqual({path.relative_to(self.root).as_posix(): path.read_bytes()
                          for path in self.root.rglob('*') if path.is_file()}, before)

    def test_saved_compose_retains_original_and_current_request_without_prior_method(self):
        parent = self.finish(self.start())
        prior = workflow.read_run(self.root, parent)
        parent_digest = prior.prepared['input_sha256']
        (self.root / 'definition.json').unlink()
        self.write('current-request.txt', 'Make their connection the point of the image.\n構図は選び直してよい。')
        draft = inputs.draft_inputs(self.root, None, 'recomposed', from_run=parent,
                                    operation='compose', request_file='current-request.txt')
        basis = c.load(self.root / draft['authoring_work']['basis'])
        choices = draft['choices']
        self.assertEqual((self.root / choices['authoring']['delivery']['file']).read_bytes(), b'')
        self.assertEqual(basis['request'], (self.root / 'current-request.txt').read_text(encoding='utf-8'))
        selected = {row['id'] for row in choices['authoring']['task']['sources']}
        self.assertIn('original', selected)
        self.assertNotIn('method', selected)
        self.assertEqual(c.decode(core.source_bytes(basis['sources']['original'])), DEFINITION)
        self.assertEqual(core.source_bytes(basis['sources']['method']), b'An earlier catalog display convention.')
        self.assertEqual(basis['baseline']['authoring']['delivery']['content'], prior.consumer['instructions'])
        child = workflow.read_run(self.root, self.finish(draft))
        self.assertEqual(child.prepared['parent']['run'], parent)
        self.assertEqual(self.source_bytes(child, draft['current_request']['source']), basis['request'].encode('utf-8'))
        self.assertEqual(c.decode(self.source_bytes(child, 'original')), DEFINITION)
        self.assertEqual(workflow.read_run(self.root, parent).prepared['input_sha256'], parent_digest)

    def test_saved_amend_uses_current_prompt_bytes_as_the_delivered_content(self):
        parent = self.finish(self.start())
        draft = inputs.draft_inputs(self.root, None, 'amended', from_run=parent, operation='amend')
        before = c.load(self.root / draft['authoring_work']['basis'])['baseline']
        new_text = 'The inset shell projects forward while its upper connection remains intact.\n'
        child = workflow.read_run(self.root, self.finish(draft, new_text))
        self.assertEqual(child.consumer['instructions'], new_text)
        self.assertNotEqual(before['authoring']['delivery']['content'], new_text)
        self.assertEqual(self.source_bytes(child, draft['current_request']['source']),
                         (self.root / 'request.txt').read_bytes())

    def test_unfinished_resume_retains_acquired_request_and_definition(self):
        first = self.start()
        self.write(first['choices']['authoring']['delivery']['file'], 'An unfinished shell description.')
        saved = workflow.save(self.root, first['choices_file'], draft=True)['run']
        (self.root / 'request.txt').unlink()
        (self.root / 'definition.json').unlink()
        again = inputs.draft_inputs(self.root, None, 'continued', from_run=saved, operation='amend')
        self.assertEqual((self.root / again['choices']['authoring']['delivery']['file']).read_text(encoding='utf-8'),
                         'An unfinished shell description.')
        basis = c.load(self.root / again['authoring_work']['basis'])
        self.assertEqual(basis['request'], 'Describe the shell character in a catalog display.\n')
        self.assertEqual(c.decode(core.source_bytes(basis['sources']['original'])), DEFINITION)
        self.assertEqual(basis['subjects'], {'shell': ['original']})

    def test_interrupted_publication_recovers_the_acquired_request(self):
        parent = self.finish(self.start())
        self.write('current-request.txt', 'Reconsider the shell connection from the original definition.')
        with patch.object(inputs, '_publish', side_effect=OSError('Synthetic publication interruption.')):
            with self.assertRaisesRegex(OSError, 'publication interruption'):
                inputs.draft_inputs(self.root, None, 'interrupted', from_run=parent,
                                    operation='compose', request_file='current-request.txt')
        (self.root / 'current-request.txt').unlink()
        report = inputs.inspect_inputs(self.root)
        pending = next(row for row in report['inputs'] if row['directory'] == 'interrupted')
        action = next(row for row in pending['next_actions'] if row.get('command', row.get('operation')) == 'draft-inputs')
        argv = action['argv']
        self.assertEqual(argv[argv.index('--operation') + 1], 'compose')
        retained_request = self.root / argv[argv.index('--request-file') + 1]
        self.assertEqual(retained_request.read_text(encoding='utf-8'), 'Reconsider the shell connection from the original definition.')
        completed = subprocess.run(argv, cwd=self.root, env=dict(os.environ), capture_output=True, text=True,
                                   encoding='utf-8', timeout=90)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        recovered = json.loads(completed.stdout)
        self.assertEqual(recovered['current_request']['text'], retained_request.read_text(encoding='utf-8'))
        self.assertEqual(c.load(self.root / recovered['authoring_work']['basis'])['subjects'], {'shell': ['original']})


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
