"""Public source acquisition, exact projection and recoverable draft updates.

The fixtures are synthetic source definitions. No test submits a provider
request, changes canonical adoption or supplies real authorization evidence.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import authoring_work as core
import execution_contract as c
import identity_coverage
import production_authoring as authoring
import production_authoring_work as work
import production_inputs as inputs
import production_inputs_smoke_test as fixtures
import production_source_acquisition as acquisition
from production_diagnostics import ProductionError


DEFINITION = {
    'identity': {'outline': 'A segmented oval shell with an inset sensing ring.'},
    'parts': {'pivot': 'The ring remains attached to the outer shell at two pivots.'},
    'other': {'note': 'Unselected background material stays in the original.'},
}


def source_row(**changes):
    return {'id': 'design', 'path': 'design.json', 'role': 'identity-contract',
        'disposition': 'applied', 'locator': 'Adopted identity and selected parts',
        'reason': 'The selected synthetic definition owns this comparison.',
        'identity': {'subject_ids': ['A'], 'selectors': ['/identity', '/parts']}, **changes}


def criterion(source='design', *, subjects=None):
    return {'id': 'identity', 'strength': 'hard', 'evidence': 'text',
        'text': 'Compare the selected synthetic identity.', 'identity_review': subjects or ['A'],
        'identity_bindings': [{'source': source, 'subject_ids': subjects or ['A'],
            'selectors': ['/identity'], 'treatment': 'not-exposed',
            'reason': 'This synthetic text does not depict the physical identity.',
            'carriers': [], 'variation': None}]}


def candidate(sources=None, criteria=None):
    task = {'task_id': 'synthetic-source-task', 'production_id': '01900000-0000-7000-8000-000000000010',
        'route': 'development', 'features': [], 'artifact': 'text', 'execution': 'authored',
        'sources': copy.deepcopy(sources or []),
        'criteria': copy.deepcopy(criteria or []), 'world_views': [],
        'delivery': {'path': 'delivery.txt', 'translation_notes': None},
        'direction': {'purpose': 'Inspect the synthetic source contract.',
            'intended_effect': 'Retain declared source scope.', 'basis': [], 'decisions': [],
            'source_allowances': [], 'action_slice': None, 'limitations': []},
        'authority': None, 'route_reading': 'reading.json'}
    choices = {'authoring': authoring.blank(task)}
    choices['authoring']['delivery']['content'] = 'Synthetic source comparison text.'
    return task, choices


class SourceProjectionTests(unittest.TestCase):
    def setUp(self):
        self.raw = c.encoded(DEFINITION)
        self.row = source_row()
        self.task, self.choices = candidate()
        self.current, self.basis, _ = work.begin(self.choices, task=self.task, operation='compose',
            request='Inspect the declared synthetic source.', read_source=lambda path: self.raw,
            initial=True, focus='supporting-setting')

    def test_direct_current_task_and_acquisition_share_exact_projection(self):
        task, choices = candidate([self.row])
        direct, direct_basis, _ = work.begin(choices, task=task, operation='compose',
            request=self.basis['request'], read_source=lambda path: self.raw,
            initial=True, focus='supporting-setting')
        acquired = work.acquire_source_row(self.basis, self.row, self.raw, file='design-source.json')
        direct_projection, direct_files, _ = work.project(direct_basis, direct, 'draft')
        current_projection, current_files, _ = work.project(acquired, self.current, 'draft')
        self.assertEqual(direct_projection['authoring']['task']['sources'],
                         current_projection['authoring']['task']['sources'])
        self.assertEqual(direct_files, current_files)
        self.assertEqual(direct_basis['applications'], acquired['applications'])
        self.assertEqual(direct_basis['subjects'], acquired['subjects'])
        self.assertEqual(acquired['sources']['design']['origin']['source'], self.row)
        self.assertEqual(acquired['sources']['design']['origin']['source_row'], {'file': 'design-source.json'})
        self.assertEqual(core.source_bytes(acquired['sources']['design']), self.raw)
        source = next(row for row in current_projection['authoring']['task']['sources'] if row['id'] == 'design')
        self.assertEqual(source['role'], 'identity-contract')
        self.assertEqual(source['identity'], self.row['identity'])
        self.assertEqual(source['applications'], [
            {'id': 'design:1', 'pointer': '/identity', 'subjects': ['A'], 'requirement': False},
            {'id': 'design:2', 'pointer': '/parts', 'subjects': ['A'], 'requirement': False}])

    def test_source_update_replaces_its_scope_and_retains_other_applications_and_exact_history(self):
        basis = work.acquire_source_row(self.basis, self.row, self.raw)
        note = source_row(id='note', path='note.txt', role='authorial-intent',
            identity={'subject_ids': ['B'], 'selectors': ['']}, applications=[
                {'id': 'independent-note', 'pointer': '', 'subjects': ['B'], 'requirement': True}])
        basis = work.acquire_source_row(basis, note, b'A separately selected source.')
        previous = copy.deepcopy(basis['sources']['design'])
        changed = source_row(identity={'subject_ids': ['B'], 'selectors': ['/parts']},
                             reason='The current source selection retains only the attached parts.')
        changed_raw = c.encoded({**DEFINITION, 'parts': {'pivot': 'One explicitly revised pivot.'}})
        revised = work.acquire_source_row(basis, changed, changed_raw)
        self.assertEqual(revised['applications']['design'], {'source': 'design', 'pointer': '/parts'})
        self.assertNotIn('design:1', revised['applications'])
        self.assertNotIn('design:2', revised['applications'])
        self.assertNotIn('A', revised['subjects'])
        self.assertEqual(revised['subjects']['B'], ['independent-note', 'design'])
        self.assertEqual(revised['requirements'], ['independent-note'])
        self.assertEqual(revised['applications']['independent-note'], basis['applications']['independent-note'])
        captured = 'design:captured:' + c.content_id(previous)
        self.assertEqual(revised['sources'][captured], previous)
        self.assertEqual(core.source_bytes(revised['sources'][captured]), self.raw)
        self.assertEqual(work.acquire_source_row(revised, changed, changed_raw), revised)
        self.assertEqual(basis['sources']['design'], previous)

    def test_general_source_needs_no_identity_and_can_be_retained_without_current_application(self):
        row = source_row(role='authorial-intent', path='intent.txt')
        row.pop('identity')
        acquired = work.acquire_source_row(self.basis, row, b'Preserve the selected narrative register.\n')
        projected, _, _ = work.project(acquired, self.current, 'draft')
        selected = next(item for item in projected['authoring']['task']['sources'] if item['id'] == 'design')
        self.assertEqual(selected['role'], 'authorial-intent')
        self.assertNotIn('identity', selected)
        self.assertEqual(acquired['subjects'], {})
        self.assertEqual(work.projection_diagnostics(acquired, projected), [])
        row['disposition'] = 'considered-not-used'
        revised = work.acquire_source_row(acquired, row, b'Preserve the selected narrative register.\n')
        self.assertIn('design', revised['sources'])
        self.assertNotIn('design', revised['applications'])

    def test_invalid_role_selector_and_subject_application_scope_keep_original_basis(self):
        before = copy.deepcopy(self.basis)
        missing_role = source_row()
        missing_role.pop('role')
        mismatch = source_row(applications=[
            {'id': 'design', 'pointer': '/identity', 'subjects': ['B'], 'requirement': False}])
        cases = [
            (missing_role, 'INPUT_CONSISTENCY_ERROR', 'source-row-invalid'),
            (source_row(identity={'subject_ids': ['A'], 'selectors': ['/missing']}),
             'IDENTITY_SELECTOR_MISSING', 'source-selector-missing'),
            (mismatch, 'IDENTITY_CONTRACT_INVALID', 'source-applications-mismatch'),
        ]
        for row, code, cause in cases:
            with self.subTest(cause=cause), self.assertRaises(ProductionError) as raised:
                work.acquire_source_row(self.basis, row, self.raw, file='source-row.json')
            diagnostic = raised.exception.diagnostic.as_dict()
            self.assertEqual(diagnostic['code'], code)
            self.assertEqual(diagnostic['cause'], cause)
            self.assertEqual(diagnostic['repair_owner']['file'], 'source-row.json')
            self.assertIn('acquire', diagnostic['required_action'])
            self.assertEqual(self.basis, before)

    def test_application_id_collision_never_reassigns_another_sources_meaning(self):
        other = source_row(id='other', applications=[
            {'id': 'design:1', 'pointer': '/identity', 'subjects': ['A'], 'requirement': False},
            {'id': 'other-part', 'pointer': '/parts', 'subjects': ['A'], 'requirement': False}])
        basis = work.acquire_source_row(self.basis, other, self.raw)
        before = copy.deepcopy(basis)
        with self.assertRaises(ProductionError) as raised:
            work.acquire_source_row(basis, self.row, self.raw)
        self.assertEqual(raised.exception.diagnostic.details['cause'], 'source-application-id-collision')
        self.assertEqual(basis, before)

    def test_selected_original_hash_is_checked_before_source_projection(self):
        row = source_row(origin={'path': 'original.json', 'sha256': c.digest(b'other original')})
        with self.assertRaises(ProductionError) as raised:
            work.acquire_source_row(self.basis, row, self.raw)
        self.assertEqual(raised.exception.diagnostic.code, 'IDENTITY_SOURCE_CHANGED')
        self.assertEqual(raised.exception.diagnostic.details['cause'], 'source-origin-changed')

    def generic_basis(self, *, metadata=False):
        origin = {'path': 'design.json'}
        if metadata:
            row = source_row()
            row.pop('identity')
            origin = {'kind': 'studio-source', 'source': row}
        source = core.acquire_source(self.raw, format='json', origin=origin)
        return core.revise_basis(self.basis, sources={**self.basis['sources'], 'design': source},
            applications={'design:1': {'source': 'design', 'pointer': '/identity'},
                          'design:2': {'source': 'design', 'pointer': '/parts'}},
            subjects={'A': ['design:1', 'design:2']})

    def test_missing_metadata_diagnostic_traces_dropped_identity_to_the_descriptor_owner(self):
        choices = copy.deepcopy(self.current)
        choices['authoring']['task'].update(sources=[self.row], criteria=[criterion()])
        basis = self.generic_basis()
        report = work.projection_diagnostics(basis, choices, root=Path('/synthetic-studio'),
            choices_path='draft/choices.json', basis_path='draft/work-basis.json')
        self.assertEqual(len(report), 1)
        diagnostic = report[0]
        self.assertEqual(diagnostic['cause'], 'source-metadata-not-acquired')
        self.assertIn('identity', diagnostic['projection']['dropped_fields'])
        self.assertFalse(diagnostic['projection']['origin_has_source_metadata'])
        self.assertEqual(diagnostic['projection']['subjects'], ['A'])
        self.assertEqual(diagnostic['repair_action']['command'], 'acquire-source')
        self.assertNotEqual(diagnostic['repair_owner']['file'], 'draft/choices.json')
        self.assertIn('work-catalog/', diagnostic['source_row']['path'])
        self.assertEqual(diagnostic['source_row']['identity'], self.row['identity'])
        projected, files, _ = work.project(basis, choices, 'draft')
        original_path = diagnostic['source_row']['path'].removeprefix('draft/')
        self.assertEqual(files[original_path], self.raw)
        self.assertNotIn('identity', projected['authoring']['task']['sources'][0])

    def test_undeclared_identity_unknown_binding_and_subject_scope_are_distinct(self):
        choices = copy.deepcopy(self.current)
        choices['authoring']['task']['criteria'] = [criterion()]
        diagnostics = work.projection_diagnostics(self.generic_basis(metadata=True), choices)
        self.assertEqual(diagnostics[0]['cause'], 'source-identity-not-declared')
        acquired = work.acquire_source_row(self.basis, self.row, self.raw)
        for binding, expected in [(criterion('unknown'), 'identity-binding-source-unknown'),
                                  (criterion(subjects=['B']), 'identity-binding-subject-scope')]:
            with self.subTest(cause=expected):
                choices['authoring']['task']['criteria'] = [binding]
                projected, _, _ = work.project(acquired, choices, 'draft')
                self.assertEqual(work.projection_diagnostics(acquired, choices, projected=projected), [])
                with self.assertRaises(ProductionError) as raised:
                    identity_coverage.validate_task(projected['authoring']['task'])
                self.assertEqual(raised.exception.diagnostic.details['cause'], expected)
                self.assertEqual(raised.exception.diagnostic.details['repair_owner']['kind'], 'criterion')


class SourceAcquisitionTests(unittest.TestCase):
    save_choices = fixtures.InputToolsTests.save_choices
    files = fixtures.InputToolsTests.files

    def setUp(self):
        fixtures.InputToolsTests.setUp(self, draft=False)
        import work_ledger
        self.work = work_ledger.begin(self.root, 'Inspect synthetic source acquisition.', ['Acquire sources'])
        self.task['task_id'] = self.work['task_id']
        (self.root / 'task.json').write_bytes(c.encoded(self.task))
        result = fixtures.authoring_fixtures.authoring_inputs(self.root, 'task.json', 'inputs', operation='compose')
        self.choices_path = result['choices_file']
        self.choices = c.load(self.root / self.choices_path)
        self.choices['reading']['reading_key'] = self.issued['reading_key']
        self.save_choices()
        self.row = source_row()
        self.row_path = 'inputs/design-source.json'
        (self.root / 'design.json').write_bytes(c.encoded(DEFINITION))
        (self.root / self.row_path).write_bytes(c.encoded(self.row))
        self.basis_path = 'inputs/work-basis.json'

    def acquire(self):
        return acquisition.acquire_source(self.root, self.choices_path, self.row_path)

    def concurrent_acquisitions(self, rows):
        processes = []
        try:
            for name, row in rows:
                descriptor = 'inputs/' + name + '-source.json'
                (self.root / descriptor).write_bytes(c.encoded(row))
                processes.append(subprocess.Popen([sys.executable,
                    str(inputs.ROOT / 'scripts/production_workflow.py'), 'acquire-source',
                    '--root', str(self.root), '--choices', self.choices_path,
                    '--source-row', descriptor], cwd=self.root, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding='utf-8'))
            results = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=45)
                self.assertEqual(stderr, '', stderr)
                results.append((process.returncode, json.loads(stdout)))
            return results
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_two_character_acquisitions_run_concurrently_without_losing_or_mixing_sources(self):
        other = {'identity': {'outline': 'A tall triangular shell with a flat silver crown.'},
                 'parts': {'pivot': 'Three short supports remain attached to the lower edge.'}}
        (self.root / 'other.json').write_bytes(c.encoded(other))
        a = source_row(id='character-a')
        b = source_row(id='character-b', path='other.json',
                       identity={'subject_ids': ['B'], 'selectors': ['/identity', '/parts']})
        results = self.concurrent_acquisitions([('a', a), ('b', b)])
        self.assertEqual([code for code, _ in results], [0, 0], results)
        self.assertTrue(all(report['ok'] for _, report in results))
        basis = c.load(self.root / self.basis_path)
        self.assertEqual(basis['subjects']['A'], ['character-a:1', 'character-a:2'])
        self.assertEqual(basis['subjects']['B'], ['character-b:1', 'character-b:2'])
        self.assertEqual(core.source_bytes(basis['sources']['character-a']), c.encoded(DEFINITION))
        self.assertEqual(core.source_bytes(basis['sources']['character-b']), c.encoded(other))
        b_before = copy.deepcopy(basis['sources']['character-b'])
        choices = c.load(self.root / self.choices_path)
        projected_b = next(row for row in choices['authoring']['task']['sources'] if row['id'] == 'character-b')
        b_paths = [projected_b['path']]
        if projected_b.get('origin') is not None:
            b_paths.append(projected_b['origin']['path'])
        b_files = {path: (self.root / path).read_bytes() for path in b_paths}

        changed = {**DEFINITION, 'identity': {'outline': 'The same oval shell with a narrow blue rim.'}}
        (self.root / 'design.json').write_bytes(c.encoded(changed))
        updated = acquisition.acquire_source(self.root, self.choices_path, 'inputs/a-source.json')
        self.assertTrue(updated['changed'])
        current = c.load(self.root / self.basis_path)
        self.assertEqual(current['sources']['character-b'], b_before)
        self.assertEqual(current['subjects']['B'], basis['subjects']['B'])
        self.assertEqual({path: (self.root / path).read_bytes() for path in b_files}, b_files)
        self.assertEqual(core.source_bytes(current['sources']['character-a']), c.encoded(changed))
        self.assertTrue(any(key.startswith('character-a:captured:') for key in current['sources']))

    def test_concurrent_conflicting_application_ids_reject_one_writer_without_cross_assigning(self):
        (self.root / 'other.json').write_bytes(c.encoded(DEFINITION))
        rows = []
        for subject, path in [('A', 'design.json'), ('B', 'other.json')]:
            row = source_row(id='character-' + subject, path=path,
                identity={'subject_ids': [subject], 'selectors': ['/identity']},
                applications=[{'id': 'same-application', 'pointer': '/identity',
                               'subjects': [subject], 'requirement': False}])
            rows.append((subject.lower(), row))
        results = self.concurrent_acquisitions(rows)
        self.assertEqual(sorted(code for code, _ in results), [0, 2], results)
        refused = next(report for code, report in results if code)
        diagnostic = next(row for row in refused['diagnostics'] if row.get('cause') == 'source-application-id-collision')
        self.assertTrue(diagnostic['repair_owner']['file'].endswith('-source.json'))
        basis = c.load(self.root / self.basis_path)
        selected = basis['applications']['same-application']['source']
        winner = selected.removeprefix('character-')
        loser = 'B' if winner == 'A' else 'A'
        self.assertEqual(basis['subjects'][winner], ['same-application'])
        self.assertNotIn(loser, basis['subjects'])
        self.assertNotIn('character-' + loser, basis['sources'])
        choices = c.load(self.root / self.choices_path)
        declared = [row for row in choices['authoring']['task']['sources'] if row['id'].startswith('character-')]
        self.assertEqual(len(declared), 1)
        self.assertEqual(declared[0]['identity']['subject_ids'], [winner])

    def test_core_context_and_production_acquisition_share_the_same_basis_lock(self):
        from concurrent.futures import ThreadPoolExecutor
        before = c.load(self.root / self.basis_path)
        raw = b'Keep the separate second character in a red apron.\n'
        (self.root / 'second-intent.txt').write_bytes(raw)
        context = [sys.executable, str(inputs.ROOT / 'scripts/authoring_work.py'), 'context',
            str(self.root / self.basis_path), '--basis-only', '--source',
            'second-intent=' + str(self.root / 'second-intent.txt'),
            '--application', 'second-intent=second-intent#']
        for requirement in [*before['requirements'], 'second-intent']:
            context.extend(('--requirement', requirement))
        acquire = [sys.executable, str(inputs.ROOT / 'scripts/production_workflow.py'), 'acquire-source',
            '--root', str(self.root), '--choices', self.choices_path, '--source-row', self.row_path]

        def invoke(argv):
            return subprocess.run(argv, cwd=self.root, capture_output=True,
                                  text=True, encoding='utf-8', timeout=45)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(invoke, [context, acquire]))
        for result in results:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads(result.stdout)['ok'])
        basis = c.load(self.root / self.basis_path)
        self.assertEqual(core.source_bytes(basis['sources']['second-intent']), raw)
        self.assertEqual(core.source_bytes(basis['sources']['design']), c.encoded(DEFINITION))
        self.assertEqual(basis['requirements'], [*before['requirements'], 'second-intent'])
        self.assertEqual(basis['subjects']['A'], ['design:1', 'design:2'])
        # A context update owns the basis; the regular view projects its current
        # sources regardless of which of the two operations finished first.
        view = inputs.authoring_view(self.root, self.choices_path, register=False)
        selected = {row['id']: row for row in view['task']['sources']}
        self.assertIn('second-intent', selected)
        self.assertEqual(selected['design']['identity']['subject_ids'], ['A'])

    def test_registered_acquisition_publishes_projection_and_repeated_call_writes_nothing(self):
        self.choices['authoring']['task']['criteria'].append(criterion())
        self.save_choices()
        original = copy.deepcopy(self.choices)
        result = self.acquire()
        self.assertTrue(result['ok'])
        self.assertTrue(result['changed'])
        self.assertFalse(result['external_effect'])
        self.assertEqual(result['projected_source']['identity'], self.row['identity'])
        choices = c.load(self.root / self.choices_path)
        for key in ('delivery', 'documents', 'generation', 'references'):
            self.assertEqual(choices['authoring'][key], original['authoring'][key])
        for key in ('criteria', 'authority', 'direction'):
            self.assertEqual(choices['authoring']['task'][key], original['authoring']['task'][key])
        basis = c.load(self.root / self.basis_path)
        self.assertEqual(basis['sources']['design']['origin']['source'], self.row)
        self.assertEqual((self.root / result['projected_source']['path']).read_bytes(), c.encoded(DEFINITION))
        before = self.files()
        with patch.object(c, 'atomic', side_effect=AssertionError('unchanged source acquisition wrote a file')):
            again = self.acquire()
        self.assertFalse(again['changed'])
        self.assertEqual(self.files(), before)
        built = inputs.build_inputs(self.root, None, self.choices_path, 'source-built')
        self.assertTrue(built['ok'], built)

    def test_changed_bytes_and_selection_retain_previous_acquisition(self):
        first = self.acquire()
        old_basis = c.load(self.root / self.basis_path)
        raw = c.encoded({**DEFINITION, 'parts': {'pivot': 'A revised synthetic attachment.'}})
        (self.root / 'design.json').write_bytes(raw)
        self.row['identity'] = {'subject_ids': ['B'], 'selectors': ['/parts']}
        (self.root / self.row_path).write_bytes(c.encoded(self.row))
        updated = self.acquire()
        basis = c.load(self.root / self.basis_path)
        archived = 'design:captured:' + c.content_id(old_basis['sources']['design'])
        self.assertEqual(basis['sources'][archived], old_basis['sources']['design'])
        self.assertEqual((self.root / first['projected_source']['path']).read_bytes(), c.encoded(DEFINITION))
        self.assertEqual((self.root / updated['projected_source']['path']).read_bytes(), raw)
        self.assertEqual(updated['subjects'], {'B': ['design']})
        self.assertEqual(updated['applications'], {'design': {'source': 'design', 'pointer': '/parts'}})
        self.assertNotIn('A', basis['subjects'])

    def test_invalid_selector_and_missing_source_leave_every_draft_file_unchanged(self):
        for selected in [source_row(path='absent.json'),
                         source_row(identity={'subject_ids': ['A'], 'selectors': ['/absent']})]:
            with self.subTest(source=selected):
                (self.root / self.row_path).write_bytes(c.encoded(selected))
                before = self.files()
                with self.assertRaises(ProductionError):
                    self.acquire()
                self.assertEqual(self.files(), before)

    def test_failed_choices_publication_restores_basis_and_removes_only_new_derived_files(self):
        before = self.files()
        atomic = c.atomic
        failed = False

        def fail_once(path, raw, **kwargs):
            nonlocal failed
            if Path(path).resolve() == (self.root / self.choices_path).resolve() and not failed:
                failed = True
                raise OSError('synthetic choices publication interruption')
            return atomic(path, raw, **kwargs)

        with patch.object(c, 'atomic', side_effect=fail_once), self.assertRaisesRegex(OSError, 'interruption'):
            self.acquire()
        self.assertTrue(failed)
        self.assertEqual(self.files(), before)
        self.assertTrue(self.acquire()['ok'])

    def test_context_registration_is_still_checked_before_any_draft_mutation(self):
        path = self.root / 'inputs/context.json'
        value = c.load(path)
        value['task_content']['direction']['purpose'] = 'A different unregistered origin.'
        path.write_bytes(c.encoded(value))
        before = self.files()
        with self.assertRaises(ProductionError) as raised:
            self.acquire()
        self.assertEqual(raised.exception.diagnostic.code, 'AUTHORING_CONTEXT_MISMATCH')
        self.assertEqual(self.files(), before)

    def test_cli_acquires_source_row_without_a_provider_call(self):
        command = [sys.executable, str(Path(__file__).with_name('production_workflow.py')),
            'acquire-source', '--root', str(self.root), '--choices', self.choices_path,
            '--source-row', self.row_path]
        completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report['ok'])
        self.assertEqual(report['state'], 'source-acquired')
        self.assertEqual(report['projected_source']['identity'], self.row['identity'])
        self.assertFalse(report['external_effect'])

    def test_public_inspection_reports_generic_acquisition_before_check_and_accepts_its_repair(self):
        basis = c.load(self.root / self.basis_path)
        raw = (self.root / 'design.json').read_bytes()
        basis = core.revise_basis(basis,
            sources={**basis['sources'], 'design': core.acquire_source(raw, format='json',
                                                                       origin={'path': 'design.json'})},
            applications={**basis['applications'], 'design': {'source': 'design', 'pointer': '/identity'}},
            subjects={'A': ['design']})
        (self.root / self.basis_path).write_bytes(c.encoded(basis))
        self.choices['authoring']['task']['sources'].append(source_row(
            identity={'subject_ids': ['A'], 'selectors': ['/identity']}))
        self.choices['authoring']['task']['criteria'].append(criterion())
        self.save_choices()
        view = inputs.authoring_view(self.root, self.choices_path)
        gaps = [row for row in view['unresolved'] if row.get('cause') == 'source-metadata-not-acquired']
        self.assertEqual(len(gaps), 1)
        self.assertIn('identity', gaps[0]['projection']['dropped_fields'])
        self.assertEqual(gaps[0]['repair_action']['command'], 'acquire-source')
        self.acquire()
        after = inputs.authoring_view(self.root, self.choices_path)
        self.assertFalse(any(row.get('phase') == 'authoring-projection' for row in after['unresolved']))
        identity_coverage.validate_task(after['task'])


class RetainedSourceMutationTests(unittest.TestCase):
    """The public repair resumes the proposed candidate, including acquired bytes."""
    files = fixtures.InputToolsTests.files

    def setUp(self):
        from test_production_identity import IdentityAuthoringTests
        IdentityAuthoringTests.setUp(self)
        result, choices = IdentityAuthoringTests.draft_identity(self)
        self.choices_path = result['choices_file']
        self.folder = Path(self.choices_path).parent
        self.choices = choices
        (self.root / self.choices_path).write_bytes(c.encoded(choices))
        self.row = {'id': 'canon', 'path': 'replacement.json', 'role': 'identity',
            'disposition': 'applied', 'locator': 'whole original',
            'reason': 'The current synthetic source selection.',
            'identity': {'subject_ids': ['A'], 'selectors': ['']}}
        self.replacement = c.encoded({'identity': {'outline': 'A closed loop with two attached hinges.'}})
        (self.root / 'replacement.json').write_bytes(self.replacement)
        (self.root / 'source-row.json').write_bytes(c.encoded(self.row))

    def reject(self, row=None):
        if row is not None:
            (self.root / 'source-row.json').write_bytes(c.encoded(row))
        before = self.files()
        with self.assertRaises(ProductionError) as raised:
            acquisition.acquire_source(self.root, self.choices_path, 'source-row.json')
        problem = raised.exception.diagnostic.as_dict()
        self.assertEqual(problem['code'], 'IDENTITY_SOURCE_CHANGED')
        self.assertEqual(problem['cause'], 'retained-identity-source-changed')
        after = self.files()
        for path, raw in before.items():
            self.assertEqual(after[path], raw, path)
        original_files = {name for name in before if name.startswith(self.folder.as_posix() + '/')}
        self.assertEqual({name for name in after if name.startswith(self.folder.as_posix() + '/')}, original_files)
        self.assertEqual(problem['next_action'], problem['repair_action'])
        self.assertEqual(problem['repair_action']['command'], 'draft-inputs')
        self.assertEqual(problem['inspect_action']['command'], 'inspect-inputs')
        return problem

    def test_changed_source_is_rejected_before_publication_and_its_repair_consumes_captured_content(self):
        edited = b'Current authored candidate remains available.\r\n'
        delivery = self.choices['authoring']['delivery']['file']
        (self.root / delivery).write_bytes(edited)
        problem = self.reject()
        self.assertIn('content', {row['change_kind'] for row in problem['changes']})
        proposal = problem['proposed_candidate']['choices']
        self.assertIn(proposal, problem['repair_action']['argv'])
        (self.root / 'replacement.json').unlink()
        (self.root / 'source-row.json').unlink()
        (self.root / delivery).unlink()
        completed = subprocess.run(problem['repair_action']['argv'], cwd=self.root,
            capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        argv = problem['repair_action']['argv']
        output = argv[argv.index('--out-dir') + 1]
        selected = c.load(self.root / output / 'choices.json')
        self.assertEqual((self.root / selected['authoring']['delivery']['file']).read_bytes(), edited)
        basis = c.load(self.root / output / 'work-basis.json')
        self.assertEqual(basis['operation'], 'compose')
        self.assertEqual(core.source_bytes(basis['sources']['canon']), self.replacement)
        self.assertEqual(result['choices_file'], (Path(output) / 'choices.json').as_posix())

    def test_cross_task_run_revision_repair_remains_registered(self):
        import production_operations as operations
        import work_ledger

        (self.root / self.choices_path).write_bytes(c.encoded(self.choices))
        parent = operations.prepare(self.root, choices=self.choices_path)['run']
        work_ledger.suspend(self.root, reason='Open independent synthetic revision work.')
        revision = work_ledger.begin(self.root, 'Synthetic identity revision.', ['Compose'])['task_id']
        drafted = inputs.draft_inputs(self.root, None, 'cross-task-amend', from_run=parent,
                                      operation='amend', task_id=revision)
        self.choices_path = drafted['choices_file']
        self.folder = Path(self.choices_path).parent
        problem = self.reject()
        completed = subprocess.run(problem['repair_action']['argv'], cwd=self.root,
            capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        inspection = subprocess.run([sys.executable, str(Path(__file__).with_name('production_workflow.py')),
            'inspect-inputs', '--root', str(self.root), '--choices', result['choices_file'], '--view', 'summary'],
            cwd=self.root, capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(inspection.returncode, 0, inspection.stdout + inspection.stderr)
        report = json.loads(inspection.stdout)
        self.assertEqual(report['choices_file'], result['choices_file'])
        self.assertFalse(any(row.get('code') == 'AUTHORING_STATE_UNREADABLE'
                             for row in report['diagnostics']), report)
        context = c.load(self.root / result['context_file'])
        self.assertEqual(context['task_binding'], {'task_id': revision})
        self.assertEqual(context['derived_from']['source_run']['run'], parent)

    def test_exclusion_uses_retained_bytes_when_original_is_unavailable(self):
        original = next(row for row in self.choices['authoring']['task']['sources'] if row['id'] == 'canon')
        excluded = {key: copy.deepcopy(value) for key, value in original.items()
                    if key not in {'identity', 'applications', 'origin'}}
        excluded.update(disposition='considered-not-used', path='missing-original.json')
        problem = self.reject(excluded)
        self.assertIn('removed', {row['change_kind'] for row in problem['changes']})

    def test_addition_to_retained_identity_set_is_rejected(self):
        added = {**self.row, 'id': 'new-identity'}
        problem = self.reject(added)
        self.assertIn('added', {row['change_kind'] for row in problem['changes']})


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
