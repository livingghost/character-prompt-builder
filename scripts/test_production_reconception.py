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
    def test_initial_compose_keeps_declared_authority_and_rebinds_current_sources(self):
        task, choices = plain_choices()
        task.update(authority='explicit-authority.json', execution_decisions='previous-decisions.json')
        task['sources'] = [source_row('definition', 'definition.json')]
        choices['authoring'] = authoring.blank(task)
        material = {'definition.json': c.encoded(DEFINITION), 'mask.png': b'Synthetic mask input.'}
        current, prior, current_task = adapter.begin(choices, task=task, operation='compose',
            request='Use the declared synthetic inputs.', read_source=material.__getitem__, initial=True)
        self.assertEqual(current_task['authority'], 'explicit-authority.json')
        self.assertEqual(current['authoring']['task']['authority'], 'explicit-authority.json')
        self.assertNotIn('execution_decisions', current_task)
        self.assertNotIn('execution_decisions', current['authoring']['task'])
        current_task['sources'].append(source_row('mask', 'mask.png'))
        current['authoring']['task'] = copy.deepcopy(current_task)
        repeated, basis, repeated_task = adapter.begin(current, task=current_task,
            operation='compose', request=prior['request'], read_source=material.__getitem__,
            prior_basis=prior, initial=True)
        projected, _, _ = adapter.project(basis, repeated, 'editing')
        self.assertEqual(repeated_task['authority'], 'explicit-authority.json')
        self.assertEqual({row['id'] for row in projected['authoring']['task']['sources']}
                         - {'request:' + c.digest(prior['request'].encode('utf-8'))}, {'definition', 'mask'})
        self.assertEqual(basis['applications']['mask'], {'source': 'mask', 'pointer': ''})
        reopened, _, reopened_task = adapter.begin(current, task=current_task,
            operation='compose', request=prior['request'], read_source=material.__getitem__, prior_basis=prior)
        self.assertIsNone(reopened_task['authority'])
        self.assertIsNone(reopened['authoring']['task']['authority'])

    def test_initial_declared_grant_reaches_preparation_and_execution_decisions(self):
        import production_execution
        import production_store
        from catalog_retrieval import runtime
        with tempfile.TemporaryDirectory(prefix='cpb-initial-authority-') as temporary:
            base = Path(temporary)
            with fixtures.scratch_home(base / 'home'), patch.dict(os.environ):
                self.addCleanup(runtime.configure_pack_runtime, None)
                case = cases.create(base / 'studio', base / 'runtime')
                self.assertEqual(case['task']['authority'], 'fixture-authority.json')
                prepared = workflow.prepare(case['root'], 'task.json')
                held = production_store.authority(case['root'], case['task']['task_id'])
                self.assertEqual(held['grants'][0]['id'], 'fixture-grant')
                decisions = production_execution.draft_execution(case['root'], prepared['run'], 'fixture-grant')
                self.assertTrue(decisions['choices']['decisions'])

    def test_constructor_recovery_does_not_offer_compose_for_missing_current_evidence(self):
        from production_diagnostics import ProductionError
        actions = inputs._constructor_identity_actions(Path('/synthetic-studio'), 'new-compose',
            {'task': 'task.json'}, None)
        with self.assertRaises(ProductionError) as raised:
            inputs._require_constructor_identity({'sources': [], 'unresolved': []},
                {'sources': [], 'unresolved': [{'owner': 'authoring.references',
                    'message': 'The selected current source is unavailable.'}]},
                {'operation': 'amend'}, file='task.json', out_dir='new-compose', actions=actions)
        diagnostic = raised.exception.diagnostic.as_dict()
        self.assertEqual(diagnostic['code'], 'IDENTITY_SOURCE_UNAVAILABLE')
        self.assertNotIn('repair_action', diagnostic)
        self.assertNotIn('next_action', diagnostic)

    def test_task_normalization_preserves_each_specialist_selection_owner(self):
        task, choices = plain_choices()
        task['semantic_edit'] = 'original-plan.json'
        choices['authoring']['task']['semantic_edit'] = 'imported-plan.json'
        selected = {'world_views': [{'plan': 'world-plan.json', 'bundle': 'world-bundle'}],
            'moment_views': [{'query': 'moment-query.json', 'bundle': 'moment-bundle'}],
            'scene_materials': [{'plan': 'scene-plan.json', 'bundle': 'scene-bundle'}],
            'upload_sources': [{'file': 'carrier.png', 'url': 'https://example.test/carrier.png'}],
            'direction': {**task['direction'], 'purpose': 'The current purpose.'}}
        changes = {'semantic_edit': 'current-plan.json', 'delivery': {'path': 'derived-delivery.json'},
                   'generation': {'references': 'derived-references.json'}}
        choices['task_changes'] = {**selected, **changes}
        normalized = inputs.normalize_task_choices(choices)
        self.assertEqual(normalized['task_changes'], changes)
        self.assertNotIn('semantic_edit', normalized['authoring']['task'])
        for key, value in selected.items():
            self.assertEqual(normalized['authoring']['task'][key], value)
        self.assertEqual(inputs._chosen_task(task, normalized)['semantic_edit'], 'current-plan.json')
        del normalized['task_changes']['semantic_edit']
        self.assertNotIn('semantic_edit', inputs._chosen_task(task, normalized))

    def test_recomposition_keeps_the_original_protected_requirement_evidence(self):
        task, choices = plain_choices()
        original = {'id': 'connection', 'strength': 'hard', 'evidence': 'artifact',
                    'text': 'The shells remain connected.'}
        task['criteria'] = [original]
        choices['authoring'] = authoring.blank(task)
        current, basis, _ = adapter.begin(choices, task=task, operation='compose',
            request='Describe the connection.', read_source=lambda _: b'',
            protected_criteria={'connection'}, focus='supporting-setting')
        current, files, _ = adapter.project(basis, current, 'first')
        current['authoring']['task']['criteria'][0]['text'] = 'The shells can separate.'
        revised, retained, _ = adapter.begin(current, task=current['authoring']['task'],
            operation='compose', request='Select a fresh depiction.', prior_basis=basis,
            read_source=lambda path: files[path.removeprefix('first/')],
            protected_criteria={'connection'}, focus='supporting-setting')
        report = adapter.unresolved(retained, revised)
        gap = next(item for item in report if item.get('cause') == 'protected-requirement-changed')
        self.assertEqual(gap['expected'], original)
        self.assertEqual(gap['actual']['text'], 'The shells can separate.')
        self.assertEqual(retained['requirements'], basis['requirements'])

    def test_protected_requirement_comparison_is_shared_by_draft_and_completed_task(self):
        from production_diagnostics import ProductionError
        task, choices = plain_choices()
        criterion = {'id': 'connection', 'strength': 'hard', 'evidence': 'artifact',
                     'text': 'The two shells remain connected.'}
        task['criteria'] = [criterion]
        choices['authoring'] = authoring.blank(task)
        current, basis, _ = adapter.begin(choices, task=task, operation='compose',
            request='Describe the connection.', read_source=lambda _: b'',
            protected_criteria={'connection'}, focus='supporting-setting')
        current, files, _ = adapter.project(basis, current, 'editing')
        current['authoring']['delivery']['content'] = 'The two shells are joined.'
        before = c.encoded(basis)
        self.assertEqual(adapter.unresolved(basis, current), [])
        changed = {**criterion, 'text': 'The two shells can separate under the explicit new request.'}
        current['authoring']['task']['criteria'] = [changed]
        diagnostic = adapter.unresolved(basis, current, choices_path='editing/choices.json')[0]
        self.assertEqual((diagnostic['cause'], diagnostic['file'], diagnostic['pointer']),
                         ('protected-requirement-changed', 'editing/work-basis.json', '/requirements/0'))
        self.assertEqual(diagnostic['expected'], criterion)
        self.assertEqual(diagnostic['actual'], changed)
        self.assertEqual(diagnostic['current_criterion_owner'],
                         {'file': 'editing/choices.json', 'pointer': '/authoring/task/criteria/0'})
        material = {'editing/' + path: raw for path, raw in files.items()}
        with self.assertRaises(ProductionError) as caught:
            adapter.resolve_task_work(current['authoring']['task'], basis=basis,
                delivery=current['authoring']['delivery']['content'], documents={},
                read_source=material.__getitem__)
        actual = caught.exception.diagnostic.as_dict()
        for key in ('code', 'cause', 'application', 'criterion', 'expected', 'actual'):
            self.assertEqual(actual[key], diagnostic[key])
        self.assertEqual(c.encoded(basis), before)
        current['authoring']['task']['criteria'] = [criterion]
        current['task_changes'] = {'criteria': [changed]}
        overridden = adapter.unresolved(basis, current, choices_path='editing/choices.json')[0]
        self.assertEqual(overridden['actual'], changed)
        self.assertEqual(overridden['current_criterion_owner'],
                         {'file': 'editing/choices.json', 'pointer': '/task_changes/criteria/0'})
        from validate import markdown_anchor_slugs
        document, anchor = overridden['guidance']['document_path'].split('#')
        self.assertIn(anchor, markdown_anchor_slugs(inputs.ROOT / document))

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

    def test_compose_seeds_selected_content_and_keeps_the_comparison_baseline(self):
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
        self.assertEqual(current['authoring']['task']['direction']['decisions'], task['direction']['decisions'])
        self.assertEqual(current['authoring']['task']['direction']['source_allowances'], [allowance])
        self.assertEqual(current['authoring']['task']['criteria'], task['criteria'])
        self.assertEqual(current['target'], choices['target'])
        self.assertEqual(current['authoring']['delivery']['content'], 'The old display text.')
        self.assertIn('method', {row['id'] for row in current['authoring']['task']['sources']})
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

    def test_composed_definition_keeps_its_current_document_owner_after_publication(self):
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
        self.assertEqual(source['definition_owner'], {'document': 'production_spec', 'subject_id': 'shell'})
        reopened, acquired, _ = adapter.begin(current, task=current['authoring']['task'], operation='amend',
            request=retained['request'], read_source=lambda path: current_files[path.removeprefix('composed/')])
        selected = core.resolve_work({'basis': acquired, 'content': reopened}, require_subject=True)['context']
        self.assertEqual(selected['applications']['task-subject:shell']['value'], [DEFINITION['body']])
        current['authoring']['documents']['production_spec']['subjects'][0]['identity'] = ['Changed current definition.']
        changed_basis = adapter.bind_task_subjects(retained, current)
        selected = core.resolve_work({'basis': changed_basis, 'content': current}, require_subject=True)['context']
        self.assertEqual(selected['applications']['task-subject:shell']['value'], ['Changed current definition.'])
        self.assertEqual(retained['baseline']['authoring']['documents']['production_spec']['subjects'][0]['identity'],
                         [DEFINITION['body']])


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

    def identity_candidate_with_inactive_alternate(self):
        original = next(row for row in self.task['sources'] if row['id'] == 'original')
        original['identity'] = {'subject_ids': ['shell'], 'selectors': ['/body']}
        original.pop('applications', None)
        alternate = source_row('alternate', 'alternate.json', role='identity-contract')
        alternate['identity'] = {'subject_ids': ['shell'], 'selectors': ['/body']}
        self.task['sources'].append(alternate)
        self.task['criteria'][0].update(identity_review=['shell'], identity_bindings=[{
            'source': 'original', 'subject_ids': ['shell'], 'selectors': ['/body'],
            'treatment': 'not-exposed', 'reason': 'The synthetic text does not depict the physical identity.',
            'carriers': [], 'variation': None}])
        self.write('alternate.json', {'body': 'An independently acquired triangular shell.'})
        basis = fixtures.bind_work_basis(self.root, self.task)
        removed = {key for key, row in basis['applications'].items() if row['source'] == 'alternate'}
        basis = core.revise_basis(basis,
            applications={key: row for key, row in basis['applications'].items() if key not in removed},
            subjects={key: [item for item in rows if item not in removed]
                      for key, rows in basis['subjects'].items()})
        selected, files, _ = adapter.project(basis, {'authoring': authoring.blank(self.task)},
                                             'fixture-authoring/inactive-alternate')
        files['work-basis.json'] = c.encoded(basis)
        adapter.publish_sources(self.root, 'fixture-authoring/inactive-alternate', files)
        self.task.update(selected['authoring']['task'])
        self.write('task.json', self.task)
        return self.task

    def assert_constructor_preserves_retained_selection(self, *, task_path=None, from_run=None):
        from production_diagnostics import ProductionError
        import production_authoring_state as state
        self.write('revised-request.txt', 'Use the independently selected triangular shell.\r\n')
        work_ledger.suspend(self.root, reason='Retain the original while opening independent synthetic work.')
        def current_files():
            # Read-only SQLite connections may create empty WAL/shared-memory
            # sidecars. The database and every authored/registered record stay.
            return {path.relative_to(self.root).as_posix(): path.read_bytes()
                    for path in self.root.rglob('*') if path.is_file()
                    and not path.name.endswith(('.sqlite3-wal', '.sqlite3-shm'))}
        before = current_files()
        old_task = state.active_task_id(self.root)
        with self.assertRaises(ProductionError) as raised:
            inputs.draft_inputs(self.root, task_path, 'proposed-amend', from_run=from_run,
                operation='amend', request_file='revised-request.txt', apply_sources=['alternate'],
                focus='character', route='development', artifact='text', execution='authored',
                features=['vocabulary'], stage='depiction', new_task='Compose the selected new shell.')
        diagnostic = raised.exception.diagnostic.as_dict()
        self.assertEqual(diagnostic['code'], 'IDENTITY_SOURCE_CHANGED')
        self.assertEqual(diagnostic['cause'], 'retained-identity-source-changed')
        self.assertIn(('alternate', 'added'),
                      {(row['source'], row['change_kind']) for row in diagnostic['changes']})
        self.assertFalse((self.root / 'proposed-amend').exists())
        self.assertEqual(state.active_task_id(self.root), old_task)
        self.assertEqual(current_files(), before)
        action = diagnostic['next_actions'][0]
        self.assertEqual(diagnostic['next_action'], action)
        self.assertEqual(diagnostic['repair_action'], action)
        self.assertEqual(diagnostic['repair_owner'],
                         {'file': 'proposed-amend/choices.json', 'operation': 'compose'})
        self.assertEqual(diagnostic['next_actions'][1], diagnostic['inspect_action'])
        self.assertEqual(diagnostic['evidence_owner'],
                         {'run': from_run, 'pointer': '/task'} if from_run is not None
                         else {'file': task_path, 'pointer': ''})
        inspect_argv = diagnostic['inspect_action']['argv']
        source_flag = '--from-run' if from_run is not None else '--task'
        self.assertEqual(inspect_argv[inspect_argv.index(source_flag) + 1], from_run or task_path)
        self.assertNotIn('--operation', inspect_argv)
        self.assertEqual(diagnostic['required_action'], action['shown'])
        arguments = action['argv']
        expected = {'operation': 'compose', 'out-dir': 'proposed-amend',
            'request-file': 'revised-request.txt', 'apply-source': 'alternate', 'focus': 'character',
            'route': 'development', 'artifact': 'text', 'execution': 'authored',
            'feature': 'vocabulary', 'stage': 'depiction', 'new-task': 'Compose the selected new shell.',
            **({'from-run': from_run} if from_run is not None else {'task': task_path})}
        for key, value in expected.items():
            self.assertEqual(arguments[arguments.index('--' + key) + 1], value, key)
        completed = subprocess.run(arguments, cwd=self.root, env=dict(os.environ), capture_output=True,
                                   text=True, encoding='utf-8', timeout=90)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result['authoring_work']['operation'], 'compose')
        self.assertEqual(result['current_request']['text'], 'Use the independently selected triangular shell.\r\n')
        self.assertEqual({row['id'] for row in result['retained_identity_sources']['sources']}, {'original', 'alternate'})
        self.assertNotEqual(state.active_task_id(self.root), old_task)
        return result

    def test_task_amend_constructor_checks_before_applying_additional_identity(self):
        self.identity_candidate_with_inactive_alternate()
        self.assert_constructor_preserves_retained_selection(task_path='task.json')

    def test_unfinished_amend_constructor_compares_the_saved_identity_selection(self):
        self.identity_candidate_with_inactive_alternate()
        saved = workflow.save(self.root, self.start()['choices_file'], draft=True)['run']
        self.assert_constructor_preserves_retained_selection(from_run=saved)

    def test_finished_amend_constructor_compares_the_saved_identity_selection(self):
        self.identity_candidate_with_inactive_alternate()
        saved = self.finish(self.start())
        self.assert_constructor_preserves_retained_selection(from_run=saved)

    def test_current_choices_compose_preserves_shared_field_files_and_task_values(self):
        draft = self.start()
        choices = c.load(self.root / draft['choices_file'])
        shared = {'prompt': 'A shell beside a narrow ledge.\r\nA second literal line.\r\n',
                  'parameters': {'steps': 17}, 'untouched': 'first/prompt.txt'}
        shared_raw = (json.dumps(shared, indent=2) + '\r\n').encode('utf-8')
        (self.root / 'context.json').write_bytes(shared_raw)
        choices['authoring']['delivery'] = {'file': 'context.json', 'field': ['prompt'],
                                            'translation_notes': 'Keep the source wording.'}
        choices['authoring']['documents']['parameters'] = {'file': 'context.json', 'field': ['parameters']}
        choices['authoring']['generation'].update(count=2, seed=41)
        choices['authoring']['task']['recording'] = {'subject_map': {'shell': 'synthetic-shell'}}
        direction = copy.deepcopy(choices['authoring']['task']['direction'])
        direction['purpose'] = 'Current unsaved purpose.'
        choices['task_changes']['direction'] = direction
        choices['authoring_stage'] = 'rendition'
        self.write(draft['choices_file'], choices)
        before = (self.root / draft['choices_file']).read_bytes()
        result = inputs.draft_inputs(self.root, None, 'fresh', source_choices=draft['choices_file'])
        selected = result['choices']
        prompt = selected['authoring']['delivery']
        parameters = selected['authoring']['documents']['parameters']
        self.assertEqual(prompt['file'], parameters['file'])
        self.assertEqual(prompt['field'], ['prompt'])
        self.assertEqual(parameters['field'], ['parameters'])
        self.assertEqual((self.root / prompt['file']).read_bytes(), shared_raw)
        self.assertEqual(selected['authoring']['generation'], choices['authoring']['generation'])
        self.assertEqual(selected['authoring']['task']['recording'], choices['authoring']['task']['recording'])
        self.assertEqual(selected['authoring']['task']['direction']['purpose'], direction['purpose'])
        self.assertNotIn('direction', selected['task_changes'])
        self.assertEqual(selected['authoring']['task']['criteria'], choices['authoring']['task']['criteria'])
        self.assertEqual(selected['authoring_stage'], 'rendition')
        self.assertEqual(selected['reading'], choices['reading'])
        self.assertEqual((self.root / draft['choices_file']).read_bytes(), before)
        (self.root / 'context.json').unlink()
        view = inputs.authoring_view(self.root, result['choices_file'])
        self.assertEqual(view['delivery'], shared['prompt'].encode('utf-8'))

    def test_semantic_plan_edits_and_candidate_capture_keep_the_public_selector(self):
        import production_edit_inputs
        draft = self.start()
        plan = production_edit_inputs.plan_template()
        for name, target in (('edit-a.json', 'First synthetic target.'),
                             ('edit-b.json', 'Second synthetic target.')):
            plan['edit']['target'] = target
            self.write(name, plan)
        def edit(operation, selected=None):
            argv = [sys.executable, str(inputs.ROOT / 'scripts/production_workflow.py'),
                'edit-choices', '--root', str(self.root), '--choices', draft['choices_file'],
                '--pointer', '/task_changes/semantic_edit', '--operation', operation]
            if selected is not None:
                (self.root / 'selected-plan.json').write_bytes(c.encoded(selected))
                argv.extend(('--value-file', 'selected-plan.json'))
            completed = subprocess.run(argv, cwd=self.root, env=dict(os.environ), capture_output=True,
                                       text=True, encoding='utf-8', timeout=90)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            result = json.loads(completed.stdout)
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['edit']['owner'],
                             {'file': draft['choices_file'], 'pointer': '/task_changes/semantic_edit'})
            return c.load(self.root / draft['choices_file'])
        added = edit('add', 'edit-a.json')
        self.assertEqual(added['task_changes']['semantic_edit'], 'edit-a.json')
        replaced = edit('replace', 'edit-b.json')
        self.assertNotIn('semantic_edit', replaced['authoring']['task'])
        self.assertEqual(inputs.authoring_view(self.root, draft['choices_file'])['task']['semantic_edit'], 'edit-b.json')
        expected = (self.root / 'edit-b.json').read_bytes()
        composed = inputs.draft_inputs(self.root, None, 'plan-compose', source_choices=draft['choices_file'])
        path = composed['choices']['task_changes']['semantic_edit']
        self.assertTrue(path.startswith('plan-compose/'))
        self.assertEqual((self.root / path).read_bytes(), expected)
        (self.root / 'edit-a.json').unlink()
        (self.root / 'edit-b.json').unlink()
        view = inputs.authoring_view(self.root, composed['choices_file'])
        self.assertEqual(view['task']['semantic_edit'], path)
        self.assertEqual((self.root / path).read_bytes(), expected)
        removed = edit('remove')
        self.assertNotIn('semantic_edit', removed['task_changes'])
        self.assertNotIn('semantic_edit', inputs.authoring_view(self.root, draft['choices_file'])['task'])

    def test_proposed_candidate_survives_missing_originals_and_rejects_tampering(self):
        import production_candidate_snapshot as snapshots
        import shutil
        draft = self.start()
        choices = c.load(self.root / draft['choices_file'])
        basis = c.load(self.root / draft['authoring_work']['basis'])
        choices['authoring']['task']['direction']['purpose'] = 'The fully proposed candidate.'
        prompt_path = choices['authoring']['delivery']['file']
        proposed = b'The proposed shell is already edited.\r\n'
        before_choices = (self.root / draft['choices_file']).read_bytes()
        before_basis = (self.root / draft['authoring_work']['basis']).read_bytes()
        saved = snapshots.preserve_proposal(self.root, draft['choices_file'],
            choices=choices, basis=basis, files={prompt_path: proposed}, details={'operation': 'synthetic-edit'})
        self.assertEqual((self.root / draft['choices_file']).read_bytes(), before_choices)
        self.assertEqual((self.root / draft['authoring_work']['basis']).read_bytes(), before_basis)
        self.assertEqual(snapshots.inspect(self.root, saved['choices_file'])['state'], 'proposed-input')
        shutil.rmtree(self.root / 'first')
        result = inputs.draft_inputs(self.root, None, 'fresh', source_choices=saved['choices_file'])
        self.assertEqual((self.root / result['choices']['authoring']['delivery']['file']).read_bytes(), proposed)
        self.assertEqual(result['choices']['authoring']['task']['direction']['purpose'],
                         'The fully proposed candidate.')
        snapshot_path = self.root / saved['choices_file']
        shutil.copytree(snapshot_path.parent, self.root / 'unregistered-copy')
        with self.assertRaises((ValueError, OSError)):
            snapshots.acquire(self.root, 'unregistered-copy/choices.json')
        snapshot_path.write_bytes(snapshot_path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'snapshot member changed'):
            snapshots.acquire(self.root, saved['choices_file'])

    def test_choices_source_has_one_compose_operation(self):
        from production_diagnostics import ProductionError
        first = self.start()
        with self.assertRaises(ProductionError) as caught:
            inputs.draft_inputs(self.root, None, 'wrong-operation',
                source_choices=first['choices_file'], operation='amend')
        self.assertEqual(caught.exception.diagnostic.details['cause'], 'candidate-source-operation')
        self.assertFalse((self.root / 'wrong-operation').exists())

    def test_proposal_publication_failure_leaves_no_registered_candidate(self):
        import production_candidate_snapshot as snapshots
        import production_authoring_state as state
        draft = self.start()
        choices = c.load(self.root / draft['choices_file'])
        basis = c.load(self.root / draft['authoring_work']['basis'])
        before = {path.relative_to(self.root).as_posix(): path.read_bytes()
                  for path in self.root.rglob('*') if path.is_file()}
        for owner, method in ((inputs, '_publish'), (state, '_remember')):
            with self.subTest(failure=method):
                with patch.object(owner, method, side_effect=OSError('Synthetic snapshot publication failure.')):
                    with self.assertRaisesRegex(OSError, 'snapshot publication failure'):
                        snapshots.preserve_proposal(self.root, draft['choices_file'], choices=choices, basis=basis)
                after = {path.relative_to(self.root).as_posix(): path.read_bytes()
                         for path in self.root.rglob('*') if path.is_file()}
                self.assertEqual(after, before)

    def test_all_candidate_sources_apply_current_route_and_feature_arguments(self):
        first = self.start()
        saved = workflow.save(self.root, first['choices_file'], draft=True)['run']
        sources = ({'task_path': 'task.json'}, {'task_path': None, 'from_run': saved},
                   {'task_path': None, 'source_choices': first['choices_file']})
        for index, source in enumerate(sources):
            with self.subTest(source=source):
                drafted = inputs.draft_inputs(self.root, out_dir='selected-' + str(index),
                    operation='compose', route='prompt-only', artifact='json', execution='authored',
                    features=['vocabulary'], **source)
                current = drafted['choices']['authoring']['task']
                self.assertEqual((current['route'], current['artifact'], current['execution'], current['features']),
                                 ('prompt-only', 'json', 'authored', ['vocabulary']))
                self.assertEqual(drafted['choices']['reading'], first['choices']['reading'])
                self.assertTrue(any(row.get('code') == 'TARGET_GUIDANCE_REQUIRED'
                                    for row in drafted['unresolved']), drafted['unresolved'])

    def test_bounded_domain_inputs_keep_their_exact_graph_and_consumers_after_relocation(self):
        import shutil
        import world_realization as world
        import world_realization_smoke_test as world_fixture
        import story_context as moment
        import story_context_smoke_test as moment_fixture
        import scene_persona as scene
        import scene_material_smoke_test as scene_fixture
        import production_candidate_snapshot as snapshots
        first = self.start()
        choices = c.load(self.root / first['choices_file'])
        world_plan = world_fixture.make_fixture(self.root / 'world')
        for row in world_plan['sources']:
            row['path'] = 'world/' + row['path']
        self.write('world/plan.json', world_plan)
        world.publish(world.compile_plan(self.root, 'world/plan.json'), self.root / 'world/bundle')
        query = moment_fixture.fixture.write_inputs(self.root / 'moment')
        moment_fixture.fixture.pin(self.root / 'moment', query)
        for row in query['sources']:
            row['path'] = 'moment/' + row['path']
        self.write('moment/query.json', query)
        moment.publish(moment.materialize(self.root, 'moment/query.json'), self.root / 'moment/bundle')
        (self.root / 'scene').mkdir()
        scene_plan = scene_fixture.fixture(self.root / 'scene')
        for row in scene_plan['sources']:
            row['path'] = 'scene/' + row['path']
        self.write('scene/plan.json', scene_plan)
        scene.build(self.root, 'scene/plan.json', 'scene/material')
        material = c.load(self.root / 'scene/material/material.json')
        selections = {
            'world_views': [{'plan': 'world/plan.json', 'bundle': 'world/bundle',
                             'unit_id': 'AFTER', 'view_id': 'WRITER'}],
            'moment_views': [{'query': 'moment/query.json', 'bundle': 'moment/bundle',
                              'view_id': query['views'][0]['view_id']}],
            'scene_materials': [{'plan': 'scene/plan.json', 'bundle': 'scene/material'},
                                {'artifact': 'scene/material/material.json',
                                 'accepted_content_sha256': material['content_sha256'],
                                 'accepted_by': fixtures.ACTOR, 'acceptance_basis': 'Exact synthetic material.'}],
        }
        choices['authoring']['task'].update(selections)
        self.write(first['choices_file'], choices)
        composed = inputs.draft_inputs(self.root, None, 'bounded-compose', source_choices=first['choices_file'])
        for directory in ('world', 'moment', 'scene'):
            shutil.rmtree(self.root / directory)
        task = composed['choices']['authoring']['task']
        self.assertEqual({field: task[field] for field in selections}, selections)
        held = snapshots.retained(self.root, task, composed['candidate_inputs'])
        with held.staging():
            for field, owner in (('world_views', workflow.world_views), ('moment_views', workflow.moment_views),
                                 ('scene_materials', workflow.authoring_materials)):
                with self.subTest(field=field), held.scope(field):
                    consumed = owner(held.source_root(field), task,
                                     lambda base, path, space='studio': held.read(path))
                    self.assertTrue(consumed)
        saved = workflow.save(self.root, composed['choices_file'], draft=True)['run']
        shutil.rmtree(self.root / 'bounded-compose')
        reopened = inputs.draft_inputs(self.root, None, 'bounded-resumed', from_run=saved, operation='amend')
        self.assertEqual(reopened['choices']['authoring']['task']['moment_views'], selections['moment_views'])
        held = snapshots.retained(self.root, reopened['choices']['authoring']['task'], reopened['candidate_inputs'])
        with held.staging(), held.scope('world_views'):
            self.assertTrue(workflow.world_views(held.source_root('world_views'), reopened['choices']['authoring']['task'],
                lambda base, path, space='studio': held.read(path)))

    def test_rejected_state_owner_change_can_complete_as_a_new_compose(self):
        from test_production_identity import IdentityAuthoringTests
        from production_diagnostics import ProductionError
        from production_source_acquisition import acquire_source
        helper = IdentityAuthoringTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        first, choices = helper.draft_identity(graph=True)
        graph_file = choices['authoring']['documents']['state_graphs']['file']
        graphs = c.load(helper.root / graph_file)
        graphs[0]['identity_contract']['identity']['outline'] = 'A closed solid disc.'
        (helper.root / graph_file).write_bytes(c.encoded(graphs))
        (helper.root / first['choices_file']).write_bytes(c.encoded(choices))
        descriptor = copy.deepcopy(helper.task['sources'][0])
        descriptor['path'] = graph_file
        (helper.root / 'replacement-source.json').write_bytes(c.encoded(descriptor))
        with self.assertRaises(ProductionError) as caught:
            acquire_source(helper.root, first['choices_file'], 'replacement-source.json')
        diagnostic = caught.exception.diagnostic.as_dict()
        action = diagnostic['next_action']['argv']
        snapshot_path = action[action.index('--choices') + 1]
        composed = inputs.draft_inputs(helper.root, None, 'fresh-state', source_choices=snapshot_path)
        current = composed['choices']
        current['reading'] = copy.deepcopy(choices['reading'])
        built = helper.build_identity(composed, current, 'fresh-state-built')
        self.assertTrue(built['ok'], built.get('unresolved'))
        task = c.load(helper.root / built['inputs']['production-task']['path'])
        restored = c.load(helper.root / task['generation']['state_graphs'])
        self.assertEqual(restored[0]['identity_contract']['identity']['outline'], 'A closed solid disc.')
        self.assertEqual((helper.root / 'canon.json').read_bytes(), helper.raw)
        self.assertEqual({row['id'] for row in composed['retained_identity_sources']['sources']},
                         {'canon', 'state:A:identity_contract'})

    def test_inspect_names_retained_requirement_owners_and_public_context_repair(self):
        draft = self.start()
        basis_path = draft['authoring_work']['basis']
        basis = c.load(self.root / basis_path)
        choices = c.load(self.root / draft['choices_file'])
        previous = copy.deepcopy(choices['authoring']['task']['criteria'])
        old_id = 'retained-requirements'
        application = 'protected-requirement:1'
        original = core.acquire_source(c.encoded(previous), format='json',
            origin={'kind': 'protected-requirements', 'task_id': self.task['task_id']})
        basis = core.revise_basis(basis, sources={**basis['sources'], old_id: original},
            applications={**basis['applications'], application: {'source': old_id, 'pointer': '/0'}},
            requirements=[*basis['requirements'], application])
        self.write(basis_path, basis)
        choices['authoring']['task']['criteria'][0]['text'] = 'The explicit new request permits a separated shell.'
        self.write(draft['choices_file'], choices)
        before_basis = (self.root / basis_path).read_bytes()

        def inspect():
            report = inputs.inspect_inputs(self.root, choices_path=draft['choices_file'])
            entry = next(item for item in report['inputs'] if item['current'])
            return entry.get('working_copy', entry)['unresolved']

        gap = next(item for item in inspect() if item.get('cause') == 'protected-requirement-changed')
        self.assertEqual(gap['repair_owner']['file'], basis_path)
        self.assertEqual(gap['repair_owner']['application_pointer'], '/applications/protected-requirement:1')
        self.assertEqual(gap['current_criterion_owner'],
                         {'file': draft['choices_file'], 'pointer': '/authoring/task/criteria/0'})
        self.assertEqual(gap['expected'], previous[0])
        self.assertEqual(gap['actual'], choices['authoring']['task']['criteria'][0])
        help_result = subprocess.run(gap['next_action']['argv'], cwd=self.root,
            capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(help_result.returncode, 0, help_result.stdout + help_result.stderr)
        self.assertIn('--requirement', help_result.stdout)
        self.assertIn('--basis-only', help_result.stdout)
        self.assertEqual((self.root / basis_path).read_bytes(), before_basis)

        # The synthetic author supplies the new instruction and every intended
        # current requirement. The guide neither deletes nor approves anything.
        self.write('current-request.txt', 'Explicit synthetic instruction: allow the shell to separate.')
        self.write('current-requirements.json', choices['authoring']['task']['criteria'])
        argv = [*gap['context_edit']['argv_prefix'], '--request', str(self.root / 'current-request.txt'),
            '--source', 'current-requirements=' + str(self.root / 'current-requirements.json'),
            '--application', 'current:1=current-requirements#/0', '--requirement', 'current:1']
        repaired = subprocess.run(argv, cwd=self.root, capture_output=True,
            text=True, encoding='utf-8', timeout=30)
        self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
        self.assertFalse(any(item.get('cause') == 'protected-requirement-changed' for item in inspect()))
        retained = c.load(self.root / basis_path)
        self.assertEqual(retained['sources'][old_id], original)
        self.assertEqual(retained['requirements'], ['current:1'])
        self.assertEqual(c.load(self.root / draft['choices_file'])['authoring']['task']['criteria'],
                         choices['authoring']['task']['criteria'])

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

    def test_saved_compose_seeds_content_and_retains_original_and_current_request(self):
        parent = self.finish(self.start())
        prior = workflow.read_run(self.root, parent)
        parent_digest = prior.prepared['input_sha256']
        (self.root / 'definition.json').unlink()
        self.write('current-request.txt', 'Make their connection the point of the image.\n構図は選び直してよい。')
        draft = inputs.draft_inputs(self.root, None, 'recomposed', from_run=parent,
                                    operation='compose', request_file='current-request.txt', stage='rendition')
        basis = c.load(self.root / draft['authoring_work']['basis'])
        choices = draft['choices']
        self.assertEqual(choices['authoring_stage'], 'rendition')
        self.assertEqual((self.root / choices['authoring']['delivery']['file']).read_bytes(),
                         prior.consumer['instructions'].encode('utf-8'))
        self.assertEqual(basis['request'], (self.root / 'current-request.txt').read_text(encoding='utf-8'))
        selected = {row['id'] for row in choices['authoring']['task']['sources']}
        self.assertIn('original', selected)
        self.assertIn('method', selected)
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
                                    operation='compose', request_file='current-request.txt', stage='depiction')
        (self.root / 'current-request.txt').unlink()
        report = inputs.inspect_inputs(self.root)
        pending = next(row for row in report['inputs'] if row['directory'] == 'interrupted')
        action = next(row for row in pending['next_actions'] if row.get('command', row.get('operation')) == 'draft-inputs')
        argv = action['argv']
        self.assertEqual(argv[argv.index('--operation') + 1], 'compose')
        self.assertEqual(argv[argv.index('--stage') + 1], 'depiction')
        retained_request = self.root / argv[argv.index('--request-file') + 1]
        self.assertEqual(retained_request.read_text(encoding='utf-8'), 'Reconsider the shell connection from the original definition.')
        completed = subprocess.run(argv, cwd=self.root, env=dict(os.environ), capture_output=True, text=True,
                                   encoding='utf-8', timeout=90)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        recovered = json.loads(completed.stdout)
        self.assertEqual(recovered['choices']['authoring_stage'], 'depiction')
        self.assertEqual(recovered['current_request']['text'], retained_request.read_text(encoding='utf-8'))
        self.assertEqual(c.load(self.root / recovered['authoring_work']['basis'])['subjects'], {'shell': ['original']})


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
