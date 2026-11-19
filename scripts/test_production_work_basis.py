"""Complete task publication consumes the actual common authoring work."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

import authoring_work
import execution_contract as c
import production_compiler as compiler
import production_authoring
import production_authoring_work
import production_fixtures as fixtures
import production_inputs
import production_operations as workflow
import work_ledger
from production_diagnostics import ProductionError


class TaskWorkBasisTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.root = base / 'studio'
        self.root.mkdir()
        self.enterContext(fixtures.scratch_home(base / 'home'))
        task = work_ledger.begin(self.root, 'Develop the shell observer.', ['Compose'])
        self.request = 'Show the shell observer crossing the gap.'
        fixtures.current_request(self.root, self.request)
        self.task = {'task_id': task['task_id'], 'route': 'development', 'features': [], 'sources': [],
            'delivery': {'path': 'prompt.txt', 'translation_notes': 'Use the authored scene.'},
            'criteria': [{'id': 'scene', 'strength': 'hard', 'text': 'The observer crosses the gap.'}],
            'world_views': []}
        fixtures.task(self.root, self.task, focus='character')
        (self.root / 'prompt.txt').write_text('The shell observer braces its rim across the gap.', encoding='utf-8')
        self.write_task()

    def write_task(self):
        (self.root / 'task.json').write_bytes(c.encoded(self.task))

    def define(self):
        value = {'identity': {'body': 'An articulated shell with an inset sensing ring.'},
                 'prior_scene': {'view': 'A cabinet study from above.'}}
        (self.root / 'definition.json').write_bytes(c.encoded(value))
        self.task['sources'].append({'id': 'observer-definition', 'path': 'definition.json',
            'role': 'definition', 'disposition': 'applied', 'locator': '/identity',
            'reason': 'The current definition of the observer.',
            'applications': [{'id': 'observer', 'pointer': '/identity',
                              'subjects': ['observer'], 'requirement': False}]})
        fixtures.bind_work_basis(self.root, self.task, focus='character')
        self.write_task()
        return value

    def compilation(self):
        result = compiler.compile_task(self.root, 'task.json')
        if result.directory is not None:
            import shutil
            self.addCleanup(shutil.rmtree, result.directory, ignore_errors=True)
        return result

    def test_partial_character_definition_can_be_completed_before_raw_publication(self):
        workflow.validate_task(self.task)
        partial = self.compilation()
        self.assertFalse(partial.report['publishable'])
        self.assertIn('AUTHORING_WORK_INCOMPLETE', {row['code'] for row in partial.report['diagnostics']})
        self.define()
        completed = workflow.prepare(self.root, 'task.json')
        saved = workflow.read_run(self.root, completed['run'])
        path = saved.prepared['task']['work_basis']
        dependency = next(row for row in saved.prepared['dependencies'] if row['path'] == path)
        self.assertEqual(saved.evidence.read(dependency['sha256']), (self.root / path).read_bytes())
        self.assertEqual(saved.consumer['instructions'], (self.root / 'prompt.txt').read_text(encoding='utf-8'))

    def test_shape_allows_unselected_basis_and_completion_names_its_owner(self):
        self.task.pop('work_basis')
        self.write_task()
        workflow.validate_task(self.task)
        result = self.compilation()
        diagnostic = next(row for row in result.report['diagnostics'] if row['code'] == 'AUTHORING_WORK_INCOMPLETE')
        self.assertEqual(diagnostic['pointer'], '$.work_basis')
        self.assertIn('extract WORK --basis', diagnostic['required_action'])
        self.assertFalse(result.report['formal_run_created'])

    def test_current_request_is_acquired_before_completion(self):
        self.define()
        path = self.root / self.task['work_basis']
        basis = authoring_work.revise_basis(c.load(path), request=None)
        path.write_bytes(c.encoded(basis))
        result = self.compilation()
        self.assertFalse(result.report['publishable'])
        self.assertIn('AUTHORING_WORK_INCOMPLETE', {row['code'] for row in result.report['diagnostics']})

    def test_explicit_supporting_setting_can_complete_without_a_character(self):
        self.request = 'Prepare only the empty station platform that supports the later character scene.'
        fixtures.bind_work_basis(self.root, self.task, request=self.request, focus='supporting-setting')
        (self.root / 'prompt.txt').write_text('An empty station platform under a glass roof.', encoding='utf-8')
        self.write_task()
        result = self.compilation()
        self.assertTrue(result.report['publishable'], result.report)
        basis = c.load(self.root / self.task['work_basis'])
        self.assertEqual((basis['focus'], basis['request'], basis['subjects']),
                         ('supporting-setting', self.request, {}))

    def test_raw_task_checks_selected_source_bytes_and_application_relations(self):
        self.define()
        original = copy.deepcopy(self.task)
        (self.root / 'replacement.json').write_bytes(c.encoded({'body': 'A different closed disc.'}))
        for change in ('bytes', 'subject'):
            with self.subTest(change=change):
                self.task = copy.deepcopy(original)
                source = next(row for row in self.task['sources'] if row['id'] == 'observer-definition')
                if change == 'bytes':
                    source['path'] = 'replacement.json'
                else:
                    source['applications'][0]['subjects'] = ['another-observer']
                self.write_task()
                result = self.compilation()
                self.assertFalse(result.report['publishable'])
                self.assertIn('AUTHORING_WORK_MISMATCH', {row['code'] for row in result.report['diagnostics']})

    def test_saved_candidate_and_public_task_use_the_same_acquired_work(self):
        self.define()
        draft = fixtures.authoring_inputs(self.root, 'task.json', 'draft', focus='character')
        saved = workflow.save(self.root, draft['choices_file'])['run']
        exported = production_inputs.build_inputs(self.root, None, draft['choices_file'], 'published')
        self.assertTrue(exported['ok'], exported)
        public = workflow.prepare(self.root, exported['inputs']['production-task']['path'])['run']
        first, second = workflow.read_run(self.root, saved), workflow.read_run(self.root, public)
        self.assertEqual(first.consumer['instructions'], second.consumer['instructions'])
        first_basis = c.load(self.root / first.prepared['task']['work_basis'])
        second_basis = c.load(self.root / second.prepared['task']['work_basis'])
        self.assertEqual(first_basis, second_basis)
        self.assertEqual(first_basis['subjects'], {'observer': ['observer']})


class ApplicationProjectionOrderTests(unittest.TestCase):
    def work(self):
        task = production_authoring.seed(route='development', artifact='text',
            execution='authored', task_id='ordered-sources')
        choices = {'authoring': production_authoring.blank(task)}
        choices['authoring']['delivery']['content'] = 'The open shell turns toward the supported closed shell.'
        return authoring_work.begin_work(operation='compose',
            request='Show the two connected shell characters.',
            sources={'definitions': authoring_work.acquire_source(c.encoded({
                'front': 'An open shell with an inset ring.',
                'rear': 'A closed shell with a jointed support.'}), format='json')},
            applications={
                'z-front': {'source': 'definitions', 'pointer': '/front'},
                'a-rear': {'source': 'definitions', 'pointer': '/rear'}},
            subjects={'z-shell': ['z-front'], 'a-shell': ['z-front', 'a-rear']},
            content=choices)

    def test_projection_is_stable_across_normal_basis_storage(self):
        work = self.work()
        stored_basis = c.decode(c.encoded(work['basis']))
        first = production_authoring_work.project(work['basis'], work['content'], 'draft')
        restored = production_authoring_work.project(stored_basis, work['content'], 'draft')
        self.assertEqual(authoring_work.digest(work['basis']), authoring_work.digest(stored_basis))
        self.assertEqual(first, restored)
        choices, files, _ = first
        source = next(row for row in choices['authoring']['task']['sources'] if row['id'] == 'definitions')
        self.assertEqual([item['id'] for item in source['applications']], ['a-rear', 'z-front'])
        self.assertEqual(source['applications'][1]['subjects'], ['a-shell', 'z-shell'])
        self.assertEqual(c.decode(files[source['path'].removeprefix('draft/')]),
            ['A closed shell with a jointed support.', 'An open shell with an inset ring.'])

    def test_public_task_checks_basis_owned_order_and_projected_values(self):
        work = self.work()
        choices, projected, _ = production_authoring_work.project(work['basis'], work['content'], 'draft')
        task = choices['authoring']['task']
        task['delivery'] = {'path': 'delivery.txt', 'translation_notes': None}
        files = {'draft/' + name: raw for name, raw in projected.items()}
        files[task['work_basis']] = c.encoded(work['basis'])
        files['delivery.txt'] = choices['authoring']['delivery']['content'].encode('utf-8')
        self.assertEqual(workflow.check_authoring_work(task, read=files.__getitem__)['subjects'],
                         ['a-shell', 'z-shell'])
        for changed in ('applications', 'values', 'both'):
            with self.subTest(changed=changed):
                current_task, current_files = copy.deepcopy(task), dict(files)
                source = next(row for row in current_task['sources'] if row['id'] == 'definitions')
                if changed in {'applications', 'both'}:
                    source['applications'].reverse()
                if changed in {'values', 'both'}:
                    current_files[source['path']] = c.encoded(list(reversed(c.decode(files[source['path']]))))
                with self.assertRaises(ProductionError) as caught:
                    workflow.check_authoring_work(current_task, read=current_files.__getitem__)
                self.assertEqual(caught.exception.diagnostic.code, 'AUTHORING_WORK_MISMATCH')


class CurrentSpecificationOwnerTests(unittest.TestCase):
    def setUp(self):
        import production_case_fixtures as cases
        from catalog_retrieval import runtime
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.enterContext(fixtures.scratch_home(base / 'home'))
        case = cases.create(base / 'studio', base / 'runtime')
        self.addCleanup(runtime.configure_pack_runtime, None)
        self.root, self.task = case['root'], case['task']

    def test_current_identity_is_checked_while_body_pose_can_change(self):
        root, task = self.root, self.task
        original = c.load(root / 'spec.json')
        changed = copy.deepcopy(original)
        changed['subjects'][0]['pose_and_body_geometry'] = 'The articulated torso turns toward the opening.'
        (root / 'spec.json').write_bytes(c.encoded(changed))
        read = lambda path: c.read(root / path)
        self.assertEqual(workflow.check_authoring_work(task, read=read)['subjects'], ['robot'])
        for value in ([], [{**changed['subjects'][0], 'identity': ['A newly defined solid disc.']}]):
            with self.subTest(subjects=value):
                changed['subjects'] = value
                (root / 'spec.json').write_bytes(c.encoded(changed))
                with self.assertRaises(ProductionError) as caught:
                    workflow.check_authoring_work(task, read=read)
                self.assertEqual(caught.exception.diagnostic.code, 'AUTHORING_WORK_MISMATCH')

    def test_supporting_setting_still_checks_an_applied_task_local_definition(self):
        root, task = self.root, self.task
        path = root / task['work_basis']
        basis = authoring_work.revise_basis(c.load(path), focus='supporting-setting')
        path.write_bytes(c.encoded(basis))
        read = lambda name: c.read(root / name)
        self.assertEqual(workflow.check_authoring_work(task, read=read)['subjects'], ['robot'])
        changed = c.load(root / 'spec.json')
        changed['subjects'][0]['identity'] = ['A different solid body with two lateral fins.']
        (root / 'spec.json').write_bytes(c.encoded(changed))
        with self.assertRaises(ProductionError) as caught:
            workflow.check_authoring_work(task, read=read)
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORING_WORK_MISMATCH')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
