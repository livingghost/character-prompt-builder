"""Actual authoring content, source application and exact delivery boundaries.

These tests exercise acquired values and their consumers. They do not classify
creative intent or treat a structurally valid subject as a quality assessment.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import authoring_work as work
import protocol_contract


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = {
    'identity': {'form': 'An articulated shell with an inset sensing ring.',
                 'relation': 'The sensing ring rotates inside the outer shell.'},
    'construction': {'contact': 'The articulated rim rests against the ledge.'},
}


def basis_values():
    return {
        'request': 'Show the shell observer reaching across the gap.',
        'sources': {
            'definition': work.acquire_source(json.dumps(DEFINITION) + '\n', format='json',
                                               origin={'path': 'definition.json', 'role': 'identity'}),
            'requirement': work.acquire_source('Keep the inset ring connected at its pivot.\n'),
        },
        'applications': {
            'identity': {'source': 'definition', 'pointer': '/identity'},
            'connection': {'source': 'requirement', 'pointer': ''},
        },
        'subjects': {'observer': ['identity']},
        'requirements': ['connection'],
    }


class AuthoringWorkTests(unittest.TestCase):
    def test_compose_retains_comparison_and_starts_empty_actual_content(self):
        baseline = {'prompt': 'The observer rests inside a display cabinet.',
                    'reference_use': ['cabinet-view'], 'controls': {'treatment': 'study'}}
        values = basis_values()
        values['sources']['previous-image'] = work.acquire_source(b'\x00\xffretained image', format='binary')
        candidate = work.begin_work(operation='compose', baseline=baseline, **values)
        self.assertEqual(candidate['content'], {})
        self.assertEqual(candidate['basis']['baseline'], baseline)
        self.assertIn('previous-image', candidate['basis']['sources'])
        self.assertNotIn('previous-image', {row['source'] for row in candidate['basis']['applications'].values()})
        candidate = work.edit_value(candidate, '/prompt', 'The observer braces its rim across the gap.', operation='add')
        resolved = work.resolve_work(candidate, require_subject=True)
        self.assertEqual(resolved['content'], {'prompt': 'The observer braces its rim across the gap.'})
        self.assertEqual(resolved['context']['applications']['identity']['value'], DEFINITION['identity'])
        self.assertEqual(resolved['changes'][0]['operation'], 'add')
        self.assertTrue(any(row['pointer'] == '/reference_use' for row in resolved['comparison_changes']))

    def test_amend_owns_actual_baseline_and_exact_literal_edit(self):
        original = 'The observer steadies its rim.\r\nIts sensing ring follows the opening.\n'
        baseline = {'prompt': original, 'negative': 'An independently selected constraint.\n',
                    'controls': {'frames': [2, 7], 'label': 'Exact retained values'},
                    'documents': {'relation': DEFINITION['construction']}}
        candidate = work.begin_work(operation='amend', baseline=baseline, **basis_values())
        baseline['controls']['frames'].append(9)
        self.assertEqual(candidate['content']['controls']['frames'], [2, 7])
        changed = work.replace_text(candidate, '/prompt', 'steadies its rim', 'presses its rim against the ledge')
        self.assertEqual(candidate['content']['prompt'], original)
        self.assertEqual(changed['content']['negative'].encode(), candidate['content']['negative'].encode())
        self.assertEqual(changed['content']['controls'], candidate['content']['controls'])
        self.assertEqual(changed['content']['documents'], candidate['content']['documents'])
        expected = original.replace('steadies its rim', 'presses its rim against the ledge')
        self.assertEqual(work.candidate_value(changed, '/prompt').encode(), expected.encode())
        self.assertEqual(work.resolve_work(changed)['changes'], [
            {'operation': 'replace', 'pointer': '/prompt', 'before': original, 'after': expected}])

    def test_pointer_operations_modify_only_selected_actual_values(self):
        baseline = {'prompt': 'The rim reaches the opening.',
                    'plan': {'a/b~c': ['contact', 'pivot'], 'unrelated': {'line': 'Kept.\r\n'}},
                    'reference_ids': ['first']}
        candidate = work.begin_work(operation='amend', baseline=baseline, **basis_values())
        candidate = work.edit_value(candidate, '/plan/a~1b~0c/1', 'rim', operation='replace')
        candidate = work.edit_value(candidate, '/plan/a~1b~0c/-', 'ledge', operation='add')
        candidate = work.edit_value(candidate, '/plan/a~1b~0c/0', operation='remove')
        candidate = work.edit_value(candidate, '/reference_ids', operation='remove')
        self.assertEqual(candidate['content']['plan']['a/b~c'], ['rim', 'ledge'])
        self.assertEqual(candidate['content']['plan']['unrelated'], baseline['plan']['unrelated'])
        self.assertEqual(candidate['content']['prompt'], baseline['prompt'])
        self.assertNotIn('reference_ids', candidate['content'])
        self.assertEqual(candidate['basis']['baseline'], baseline)
        self.assertEqual({row['pointer'] for row in work.resolve_work(candidate)['changes']},
                         {'/plan/a~1b~0c', '/reference_ids'})

    def test_editable_actual_content_and_acquired_baseline_have_independent_graphs(self):
        baseline = {'prompt': 'The observer turns.', 'controls': {'positions': [1, 3]}}
        candidate = work.begin_work(operation='amend', baseline=baseline, **basis_values())
        candidate['content']['controls']['positions'].append(5)
        candidate['content']['prompt'] = 'The observer pauses at the ledge.'
        self.assertEqual(candidate['basis']['baseline'], baseline)
        self.assertTrue(work.validate_work(candidate, complete=True, require_subject=True)['ok'])

    def test_source_acquisition_preserves_exact_json_text_and_provenance(self):
        raw = b'{ "selected": {"a/b": [1, false]}, "unused": 2 }\r\n'
        origin = {'id': 'source-7', 'role': 'design', 'locator': '/selected',
                  'reason': 'Current source selection.', 'authority': {'status': 'authored'}}
        record = work.acquire_source(raw, format='json', origin=origin)
        origin['authority']['status'] = 'changed outside the acquisition'
        self.assertEqual(work.source_bytes(record), raw)
        self.assertEqual(record['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(work.source_value(record, '/selected/a~1b/1'), False)
        self.assertEqual(record['origin']['authority']['status'], 'authored')

    def test_binary_source_keeps_actual_bytes_and_supports_root_selection(self):
        raw = bytes(range(256))
        record = work.acquire_source(raw, format='binary', origin={'role': 'identity-image'})
        selected = work.source_value(record)
        self.assertEqual(work.source_bytes(selected), raw)
        self.assertIsNot(selected, record)
        with self.assertRaisesRegex(ValueError, 'empty root pointer'):
            work.source_value(record, '/shape')

    def test_acquired_request_source_and_baseline_changes_are_detected(self):
        candidate = work.begin_work(operation='amend', baseline={'prompt': 'The ring turns.'}, **basis_values())
        cases = [
            ('request', lambda row: row['basis'].__setitem__('request', 'A different exact request.')),
            ('source', lambda row: row['basis']['sources']['requirement'].__setitem__('data', 'Different source bytes.')),
            ('baseline', lambda row: row['basis']['baseline'].__setitem__('prompt', 'Changed comparison.')),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                changed = copy.deepcopy(candidate)
                mutate(changed)
                report = work.validate_work(changed)
                self.assertFalse(report['ok'])
                self.assertTrue(any('SHA-256' in row['message'] for row in report['errors']))
                with self.assertRaises(work.AuthoringWorkError):
                    work.resolve_work(changed, complete=False)

    def test_progressive_definition_is_selected_before_character_completion(self):
        candidate = work.begin_work(operation='compose', content={'prompt': 'The observer reaches.'})
        self.assertTrue(work.validate_work(candidate)['ok'])
        self.assertEqual(work.resolve_work(candidate, complete=False)['content']['prompt'], 'The observer reaches.')
        self.assertFalse(work.validate_work(candidate, complete=True, require_subject=True)['ok'])
        candidate['basis'] = work.revise_basis(candidate['basis'], request='Draw the observer.')
        self.assertFalse(work.validate_work(candidate, complete=True, require_subject=True)['ok'])
        candidate['basis'] = work.revise_basis(candidate['basis'],
            sources={'brief': work.acquire_source('A curious shell observer with a rotating inset ring.')},
            applications={'definition': {'source': 'brief', 'pointer': ''}},
            subjects={'observer': ['definition']})
        self.assertTrue(work.validate_work(candidate, complete=True, require_subject=True)['ok'])
        self.assertEqual(set(candidate['basis']['sources']), {'brief'})

    def test_acquired_context_alone_is_an_unfinished_candidate(self):
        candidate = work.begin_work(operation='compose', **basis_values())
        self.assertTrue(work.validate_work(candidate)['ok'])
        report = work.validate_work(candidate, complete=True, require_subject=True)
        self.assertFalse(report['ok'])
        self.assertEqual([row['path'] for row in report['errors']], ['/content'])

    def test_explicit_supporting_setting_has_its_actual_request(self):
        candidate = work.begin_work(operation='compose', focus='supporting-setting',
                                    request='Prepare the empty ledge setting for the observer.',
                                    content={'prompt': 'A stone ledge beside a narrow opening.'})
        self.assertTrue(work.validate_work(candidate, complete=True, require_subject=True)['ok'])
        candidate['basis'] = work.revise_basis(candidate['basis'], request=None)
        self.assertFalse(work.validate_work(candidate, complete=True, require_subject=True)['ok'])

    def test_selections_resolve_real_values_and_report_broken_references(self):
        candidate = work.begin_work(operation='compose', **basis_values())
        for pointer, change in [
            ('source', {'source': 'absent', 'pointer': '/identity'}),
            ('pointer', {'source': 'definition', 'pointer': '/absent'}),
        ]:
            with self.subTest(pointer=pointer):
                changed = copy.deepcopy(candidate)
                changed['basis']['applications']['identity'] = change
                self.assertFalse(work.validate_work(changed)['ok'])
        candidate['basis']['subjects']['observer'] = ['absent-definition']
        candidate['basis']['requirements'] = ['absent-requirement']
        report = work.validate_work(candidate)
        self.assertFalse(report['ok'])
        self.assertEqual(len(report['errors']), 2)

    def test_basis_selection_change_retains_source_catalog_and_candidate(self):
        candidate = work.begin_work(operation='compose', content={'prompt': 'The observer rests.'}, **basis_values())
        before = copy.deepcopy(candidate)
        candidate['basis'] = work.revise_basis(candidate['basis'],
            applications={'identity': candidate['basis']['applications']['identity']}, requirements=[])
        self.assertEqual(candidate['content'], before['content'])
        self.assertEqual(candidate['basis']['sources'], before['basis']['sources'])
        resolved = work.resolve_work(candidate, require_subject=True)
        self.assertEqual(set(resolved['context']['applications']), {'identity'})

    def test_explicit_reacquisition_repairs_the_selected_material_at_its_owner(self):
        candidate = work.begin_work(operation='compose', content={'prompt': 'The observer turns.'}, **basis_values())
        candidate['basis']['sources']['requirement']['data'] = 'A changed original file value.'
        self.assertFalse(work.validate_work(candidate)['ok'])
        sources = copy.deepcopy(candidate['basis']['sources'])
        sources['requirement'] = work.acquire_source('Keep the pivot joined to the shell.\n')
        candidate['basis'] = work.revise_basis(candidate['basis'], sources=sources,
                                               request='Show the revised contact relation.')
        self.assertEqual(work.resolve_work(candidate)['context']['applications']['connection']['value'],
                         'Keep the pivot joined to the shell.\n')

    def test_empty_definition_material_does_not_complete_character_work(self):
        for value in [None, {}, [], ' \r\n', b'']:
            with self.subTest(value=value):
                candidate = work.begin_work(operation='compose', request='Create a character.')
                source = work.acquire_source(value, format='binary') if isinstance(value, bytes) else work.acquire_source(json.dumps(value), format='json')
                candidate['basis']['sources']['empty'] = source
                candidate['basis']['applications']['definition'] = {'source': 'empty', 'pointer': ''}
                candidate['basis']['subjects']['subject'] = ['definition']
                self.assertFalse(work.validate_work(candidate, complete=True, require_subject=True)['ok'])

    def test_exact_text_span_checks_ambiguity_including_overlaps(self):
        candidate = work.begin_work(operation='amend', baseline={'prompt': 'aaaa'}, **basis_values())
        for old in ['aaa', '', 'missing']:
            with self.subTest(old=old):
                with self.assertRaises(ValueError):
                    work.replace_text(candidate, '/prompt', old, 'changed')
                self.assertEqual(candidate['content']['prompt'], 'aaaa')

    def test_current_json_contract_preserves_types_and_resolved_value_is_independent(self):
        candidate = work.begin_work(operation='amend', baseline={'value': True}, **basis_values())
        candidate = work.edit_value(candidate, '/value', 1)
        self.assertEqual(work.resolve_work(candidate)['changes'][0]['before'], True)
        self.assertIs(type(work.resolve_work(candidate)['changes'][0]['after']), int)
        resolved = work.resolve_work(candidate)
        resolved['content']['value'] = 9
        self.assertEqual(candidate['content']['value'], 1)
        for value in [float('nan'), (1, 2), {3: 'key'}]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    work.edit_value(candidate, '/value', value)

    def test_schema_is_supported_and_matches_current_partial_and_complete_work(self):
        schema = json.loads(work.SCHEMA.read_text(encoding='utf-8'))
        self.assertEqual(protocol_contract.unsupported_schema_keywords(schema), [])
        for candidate in [work.begin_work(operation='compose'),
                          work.begin_work(operation='amend', baseline={'prompt': 'Current actual content.'}, **basis_values())]:
            self.assertEqual(protocol_contract.validate_against_schema(candidate, schema), [])

    def test_acquired_json_and_work_require_finite_utf8_values(self):
        for text in ['{"amount": 1e400}', '{"amount": NaN}', '{"part":1,"part":2}']:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    work.acquire_source(text, format='json')
        candidate = work.begin_work(operation='compose')
        candidate['content']['prompt'] = '\ud800'
        self.assertFalse(work.validate_work(candidate)['ok'])


class AuthoringWorkComparisonTests(unittest.TestCase):
    def candidate(self, relation, content):
        values = basis_values()
        values['sources']['arrangement'] = work.acquire_source(json.dumps({
            'selected': {'construction': 'A continuous space.', 'contact': relation},
            'unused': 'A complete cabinet display.'}), format='json',
            origin={'path': relation + '.json'})
        values['sources']['shared-notes'] = work.acquire_source('The working note proposes a common construction.\n')
        values['sources']['unselected'] = work.acquire_source('Unselected source bytes remain in the catalog.\n')
        values['applications'].update({
            'arrangement': {'source': 'arrangement', 'pointer': '/selected'},
            'notes': {'source': 'shared-notes', 'pointer': ''},
        })
        return work.begin_work(operation='compose', baseline={'prompt': 'The observer sits in a cabinet.'},
                               content=content, **values)

    def test_compare_reads_whole_inputs_and_shared_selected_material(self):
        first = self.candidate('rim against ledge', {
            'prompt': 'The observer braces the rim against the ledge.\r\n',
            'negative': 'Keep the declared hinge connected.',
            'references': [{'asset': 'ledge-study', 'use': 'contact'}],
            'controls': {'steps': 4, 'strength': 0.5}})
        second = self.candidate('ring through opening', {
            'prompt': 'The inset ring reaches through the opening.\n',
            'references': [{'asset': 'opening-study', 'use': 'shape'}],
            'controls': {'steps': 4, 'strength': 0.8}})
        before = copy.deepcopy([first, second])
        report = work.compare_works([first, second], labels=['ledge', 'opening'])
        self.assertEqual(report['state'], 'intermediate')
        for row, actual in zip(report['candidates'], [first, second]):
            self.assertEqual(row['view']['content'], actual['content'])
            self.assertEqual(row['work_digest'], work.digest(actual))
            self.assertEqual(row['view']['subjects']['observer'][0]['value'], DEFINITION['identity'])
            self.assertEqual(row['view']['requirements'][0]['value'], 'Keep the inset ring connected at its pivot.\n')
            self.assertEqual(row['view']['baseline'], actual['basis']['baseline'])
            self.assertEqual(row['baseline_changes'], work.changes(actual['basis']['baseline'], actual['content']))
        common = {row['pointer']: row['value'] for row in report['common']}
        self.assertEqual(common['/other_applications/arrangement/value/construction'], 'A continuous space.')
        self.assertEqual(common['/other_applications/notes']['value'], 'The working note proposes a common construction.\n')
        self.assertEqual(common['/content/controls/steps'], 4)
        different = {row['pointer']: row['values'] for row in report['differences']}
        self.assertEqual([row['value'] for row in different['/content/prompt']],
                         [first['content']['prompt'], second['content']['prompt']])
        self.assertIn('/content/references/0/asset', different)
        self.assertIn('/other_applications/arrangement/origin/path', different)
        self.assertNotIn('Unselected source bytes', json.dumps(report))
        self.assertNotIn('A complete cabinet display.', json.dumps(report))
        report['candidates'][0]['view']['content']['controls']['steps'] = 99
        report['candidates'][0]['view']['subjects']['observer'][0]['value']['form'] = 'Edited report only.'
        self.assertEqual([first, second], before)

    def test_compare_keeps_source_assignments_and_reselected_values_visible(self):
        first = self.candidate('rim against ledge', {'prompt': 'The observer reaches.'})
        second = copy.deepcopy(first)
        applications = copy.deepcopy(second['basis']['applications'])
        applications['identity']['pointer'] = '/construction'
        del applications['notes']
        second['basis'] = work.revise_basis(second['basis'], request='Inspect the new contact.',
                                            applications=applications, requirements=[])
        report = work.compare_works([first, second])
        different = {row['pointer']: row['values'] for row in report['differences']}
        self.assertEqual([row['value'] for row in different['/request']],
                         [first['basis']['request'], 'Inspect the new contact.'])
        self.assertEqual([row['value'] for row in different['/subjects/observer/0/pointer']],
                         ['/identity', '/construction'])
        self.assertEqual(report['candidates'][1]['view']['subjects']['observer'][0]['value'],
                         DEFINITION['construction'])
        self.assertEqual([row['present'] for row in different['/requirements/0']], [True, False])
        self.assertIn('connection', report['candidates'][1]['view']['other_applications'])
        self.assertEqual([row['present'] for row in different['/other_applications/notes']], [True, False])

    def test_compare_preserves_json_types_absence_and_pointer_escaping(self):
        first = work.begin_work(operation='compose', content={
            'a/b~c': {'values': [None, True], 'optional': None}, 'empty': {}})
        second = work.begin_work(operation='compose', content={
            'a/b~c': {'values': [None, 1, 'added']}, 'empty': []})
        report = work.compare_works([first, second])
        common = {row['pointer']: row['value'] for row in report['common']}
        self.assertIsNone(common['/content/a~1b~0c/values/0'])
        different = {row['pointer']: row['values'] for row in report['differences']}
        types = different['/content/a~1b~0c/values/1']
        self.assertIs(type(types[0]['value']), bool)
        self.assertIs(type(types[1]['value']), int)
        optional = different['/content/a~1b~0c/optional']
        self.assertEqual(optional[0], {'candidate': 'candidate-1', 'present': True, 'value': None})
        self.assertEqual(optional[1], {'candidate': 'candidate-2', 'present': False})
        self.assertEqual([row['present'] for row in different['/content/a~1b~0c/values/2']], [False, True])
        self.assertEqual([row['value'] for row in different['/content/empty']], [{}, []])

    def test_compare_reads_partial_work_and_rejects_inconsistent_acquisition(self):
        partial = work.begin_work(operation='compose')
        first = work.compare_works([partial])
        self.assertEqual(first['candidates'][0]['view']['content'], {})
        self.assertIsNone(first['candidates'][0]['view']['request'])
        self.assertFalse(work.validate_work(partial, complete=True, require_subject=True)['ok'])
        actual = self.candidate('rim against ledge', {'prompt': 'The observer reaches.'})
        actual['basis']['sources']['definition']['data'] = '{"identity":"Changed bytes"}'
        with self.assertRaises(work.AuthoringWorkError):
            work.compare_works([partial, actual])


class AuthoringWorkCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cpb-authoring-work-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, CPB_HOME=str(self.root / 'home'))

    def put(self, name, value):
        path = self.root / name
        path.write_bytes(value.encode('utf-8') if isinstance(value, str) else value)
        return path

    def command(self, *arguments, code=0):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/authoring_work.py'), *map(str, arguments)],
                                cwd=self.root, env=self.env, text=True, encoding='utf-8',
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_cli_import_edit_and_export_use_one_owned_actual_content(self):
        request = self.put('request.txt', 'Show the observer reaching into the opening.\n')
        definition = self.put('definition.txt', 'An articulated shell observer with an inset ring.\n')
        # This fixture exercises literal UTF-8 and newline preservation.
        prompt = self.put('prompt.txt', '\u89b3\u6e2c\u8005\u3002 The rim is raised.\r\nThe ring turns.\n')
        negative = self.put('negative.txt', 'Selected physical constraint.\n')
        target = self.root / 'work.json'
        self.command('begin', '--operation', 'compose', '--request', request,
                     '--source', f'definition={definition}', '--application', 'subject=definition#',
                     '--subject', 'observer=subject', '--prompt', prompt, '--negative', negative, '--out', target)
        original = json.loads(target.read_bytes())
        prompt.write_text('Later edits to this acquisition file are independent.', encoding='utf-8')
        output = self.root / 'output.txt'
        self.command('check', target)
        self.command('export', target, '--out', output)
        self.assertEqual(output.read_bytes(), original['content']['prompt'].encode('utf-8'))
        old = self.put('old.txt', 'is raised')
        new = self.put('new.txt', 'rests against the ledge')
        self.command('replace-text', target, '--pointer', '/prompt', '--old-file', old, '--new-file', new)
        self.command('export', target, '--out', output)
        self.assertEqual(output.read_bytes(), original['content']['prompt'].replace('is raised', 'rests against the ledge').encode('utf-8'))
        self.assertEqual(json.loads(target.read_bytes())['content']['negative'], original['content']['negative'])

    def test_cli_progresses_from_partial_work_to_selected_definition(self):
        target = self.root / 'work.json'
        self.command('begin', '--operation', 'compose', '--out', target)
        self.command('inspect', target)
        self.command('check', target, code=1)
        request = self.put('request.txt', 'Draw a shell observer.')
        source = self.put('subject.json', '{"form":"A shell observer with an inset ring."}\n')
        self.command('context', target, '--request', request, '--source', f'source={source}',
                     '--application', 'subject=source#', '--subject', 'observer=subject')
        prompt = self.put('prompt.txt', 'The observer balances its shell across the ledge.\n')
        self.command('edit', target, '--pointer', '/prompt', '--operation', 'add', '--text-file', prompt)
        self.command('check', target)
        output = self.root / 'output.txt'
        self.command('export', target, '--out', output)
        self.assertEqual(output.read_bytes(), prompt.read_bytes())

    def test_cli_basis_only_acquires_and_removes_selections_without_another_content_owner(self):
        candidate = work.begin_work(operation='amend', request='Prepare the observer.',
                                    baseline={'prompt': 'The observer turns toward the opening.'})
        path = self.put('work-basis.json', json.dumps(candidate['basis']))
        before_baseline = copy.deepcopy(candidate['basis']['baseline'])
        definition = self.put('definition.txt', 'A shell observer with a single inset sensing ring.\n')
        request = self.put('request.txt', 'Show the shell observer looking into the opening.\n')
        result = self.command('context', path, '--basis-only', '--request', request,
                              '--source', f'brief={definition}', '--application', 'definition=brief#',
                              '--subject', 'observer=definition')
        self.assertEqual(result['basis'], str(path))
        acquired = json.loads(path.read_bytes())
        self.assertNotIn('content', acquired)
        self.assertEqual(acquired['baseline'], before_baseline)
        self.assertEqual(work.source_bytes(acquired['sources']['brief']), definition.read_bytes())
        self.assertEqual(acquired['request'], request.read_text(encoding='utf-8'))
        self.assertTrue(work.validate_work({'basis': acquired, 'content': candidate['content']},
                                          complete=True, require_subject=True)['ok'])
        original = path.read_bytes()
        self.command('context', path, '--basis-only', '--remove-application', 'definition', code=1)
        self.assertEqual(path.read_bytes(), original)
        self.command('context', path, '--basis-only', '--remove-application', 'definition',
                     '--remove-subject', 'observer')
        revised = json.loads(path.read_bytes())
        self.assertEqual(revised['applications'], {})
        self.assertEqual(revised['subjects'], {})
        self.assertEqual(revised['sources'], acquired['sources'])
        self.assertEqual(revised['baseline'], before_baseline)

    def test_cli_extracts_unfinished_actual_values_for_authoring(self):
        candidate = work.begin_work(operation='compose', content={'prompt': 'The observer pauses.\n'})
        path = self.put('work.json', json.dumps(candidate))
        extracted = self.root / 'intermediate.txt'
        report = self.command('extract', path, '--pointer', '/prompt', '--out', extracted)
        self.assertEqual(report['state'], 'intermediate')
        self.assertNotIn('input_validation', report)
        self.assertEqual(extracted.read_bytes(), candidate['content']['prompt'].encode('utf-8'))
        baseline = self.root / 'baseline.json'
        self.command('extract', path, '--pointer', '', '--out', baseline)
        self.assertEqual(json.loads(baseline.read_bytes()), candidate['content'])
        output = self.root / 'complete.txt'
        self.command('export', path, '--out', output, code=1)
        self.assertFalse(output.exists())

    def test_cli_extracts_the_actual_basis_for_a_task_without_copying_derived_context(self):
        candidate = work.begin_work(operation='compose', **basis_values())
        path = self.put('work.json', json.dumps(candidate))
        destination = self.root / 'task-basis.json'
        report = self.command('extract', path, '--basis', '--out', destination)
        self.assertEqual((report['selection'], report['pointer'], report['state']), ('basis', '', 'intermediate'))
        self.assertEqual(json.loads(destination.read_bytes()), candidate['basis'])
        subject = self.root / 'selected-subject.json'
        self.command('extract', path, '--basis', '--pointer', '/subjects', '--out', subject)
        self.assertEqual(json.loads(subject.read_bytes()), {'observer': ['identity']})

    def test_cli_compares_current_values_and_leaves_work_files_owned_by_their_editors(self):
        first = work.begin_work(operation='compose', content={'prompt': 'The observer rests.\n'})
        second = work.begin_work(operation='compose', content={'prompt': 'The observer reaches.\n'})
        paths = [self.put('first.json', json.dumps(first)), self.put('second.json', json.dumps(second))]
        original = [path.read_bytes() for path in paths]
        output = self.root / 'comparison.json'
        report = self.command('compare', *paths, '--out', output)
        self.assertEqual(report, json.loads(output.read_bytes()))
        self.assertEqual(report['state'], 'intermediate')
        self.assertEqual([row['label'] for row in report['candidates']], list(map(str, paths)))
        self.assertEqual([path.read_bytes() for path in paths], original)
        edited = self.put('edited.txt', 'The observer steadies its ring at the edge.\r\n')
        self.command('edit', paths[1], '--pointer', '/prompt', '--text-file', edited)
        refreshed = self.command('compare', *paths)
        self.assertEqual(refreshed['candidates'][1]['view']['content']['prompt'].encode(), edited.read_bytes())
        self.assertNotEqual(refreshed['candidates'][1]['work_digest'], report['candidates'][1]['work_digest'])
        self.assertEqual(json.loads(output.read_bytes()), report)
        current = paths[0].read_bytes()
        self.command('compare', *paths, '--out', paths[0], code=2)
        self.assertEqual(paths[0].read_bytes(), current)

    def test_cli_prompt_surfaces_require_actual_model_grammar_and_searched_vocabulary(self):
        import execution_contract as c
        import pack_manager as packs
        import production_case_fixtures as fixture
        from model_prompt_input_fixtures import prompt_input

        folder = self.root / 'tag-runtime'
        pack = fixture.create_pack(folder / 'pack')
        manifest = c.load(pack / 'pack.json')
        manifest['content']['resource_bindings'].update({
            'prompt-vocabulary': 'resources/dictionary.json',
            'prompt-dialects': 'resources/dialects.json'})
        fixture.write(pack / 'pack.json', manifest)
        fixture.write(pack / 'resources/dictionary.json', {
            'format': 'character-prompt-builder-prompt-vocabulary', 'name': 'Synthetic shell vocabulary',
            'description': 'Actual local lookup data for the authoring export boundary.',
            'categories': [{'id': 'shell-parts', 'name': 'Shell parts', 'description': 'Synthetic assembly terms.',
                'entries': [{'term': 'hinged shell', 'description': 'A shell joined at a working hinge.'},
                            {'term': 'pivot ring', 'description': 'An inset ring rotating at its pivot.'},
                            {'term': 'detached hinge', 'description': 'A hinge separated from its assembly.'}]}]})
        fixture.write(pack / 'resources/dialects.json', {
            'format': 'character-prompt-builder-prompt-dialects', 'name': 'Synthetic shell dialect',
            'description': 'A local input contract for this test.',
            'dialects': [{'id': 'shell-tags', 'name': 'Shell tags', 'description': 'Synthetic tag input.',
                         'vocabularies': ['shell-parts'], 'tag_separator': ', ', 'block_order': ['subject', 'assembly']}]})
        models = c.load(pack / 'records/models.json')
        model = models['records'][0]
        model.update(prompt_input=prompt_input('tag-based', vocabularies=('shell-parts',)), prompt_dialect='shell-tags')
        fixture.write(pack / 'records/models.json', models)
        packs.write_lock(pack)
        packs.save_state(folder / 'state.json', {'pack_roots': [], 'enabled_packs': [fixture.PACK_ID]})
        runtime = ['--state-file', folder / 'state.json', '--cache-dir', folder / 'cache',
                   '--managed-root', folder / 'managed', '--pack-root', pack]
        content = {'prompt': 'hinged shell, (pivot ring:1.2)\n', 'negative': '(detached hinge:1.1)',
                   'weighting': 'sdEmbeds',
                   'model_record': {key: model[key] for key in ('id', 'prompt_input', 'prompt_dialect')}}
        candidate = work.begin_work(operation='compose', content=content, **basis_values())
        path = self.put('tag-work.json', json.dumps(candidate))
        prompt, negative, model_file = self.root / 'prompt.txt', self.root / 'negative.txt', self.root / 'model.json'
        for pointer, destination in [('/prompt', prompt), ('/negative', negative), ('/model_record', model_file)]:
            report = self.command('extract', path, '--pointer', pointer, '--out', destination)
            self.assertEqual(report['state'], 'intermediate')
        output = self.root / 'completed-prompt.txt'
        for pointer in ('/prompt', '/negative'):
            blocked = self.command('export', path, '--pointer', pointer, '--out', output, *runtime, code=2)
            self.assertIn('searched vocabulary selection', json.dumps(blocked))
            self.assertFalse(output.exists())
        retrieval = self.put('retrieval.json', json.dumps({'artifact_type': 'prompt-retrieval-record', 'elements': []}))
        for operation in ('--search-vocabulary', '--settle'):
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/prompt_retrieval.py'),
                str(retrieval), operation, '--model-file', str(model_file), '--prompt-file', str(prompt),
                '--negative-file', str(negative), '--weighting', 'sdEmbeds',
                *(['--out', str(retrieval)] if operation == '--settle' else []), *map(str, runtime)],
                cwd=self.root, env=self.env, text=True, encoding='utf-8', capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        candidate['content']['documents'] = {'retrieval_record': json.loads(retrieval.read_bytes())}
        path.write_bytes(c.encoded(candidate))
        completed = self.command('export', path, '--pointer', '/prompt', '--out', output, *runtime)
        self.assertEqual(completed['state'], 'complete')
        self.assertTrue(completed['input_validation']['vocabulary_searched'])
        self.assertEqual(output.read_bytes(), prompt.read_bytes())
        candidate['content'].pop('model_record')
        candidate['content']['model'] = fixture.MODEL_ID
        path.write_bytes(c.encoded(candidate))
        negative_output = self.root / 'completed-negative.txt'
        self.command('export', path, '--pointer', '/negative', '--out', negative_output, *runtime)
        self.assertEqual(negative_output.read_bytes(), negative.read_bytes())
        candidate['content']['negative'] = '(detached hinge:1.3)'
        path.write_bytes(c.encoded(candidate))
        changed = self.command('export', path, '--out', output, *runtime, code=2)
        self.assertIn('different text', json.dumps(changed))
        self.assertEqual(output.read_bytes(), prompt.read_bytes())
        candidate['content']['prompt'] = '(hinged shell'
        path.write_bytes(c.encoded(candidate))
        grammar = self.command('export', path, '--out', output, *runtime, code=1)
        self.assertIn('TAG_PROMPT_PROBLEM', json.dumps(grammar))
        self.assertEqual(output.read_bytes(), prompt.read_bytes())


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
