"""Exercise structured edits at actual choice owners and their publication boundary.

All source bytes and work requests are synthetic. The tests publish local
drafts only; they never submit a provider request or grant authority.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import production_choice_edits as edits
import production_inputs as inputs
import production_inputs_smoke_test as fixtures
from production_diagnostics import ProductionError
from test_production_source_acquisition import candidate


def reference_choices(rows=None):
    return {'transport_mode': 'multi-image', 'max_side': 1024, 'reference_use_plan': None,
        'reference_selection': None, 'additional_references': copy.deepcopy(rows or []),
        'image_input': None, 'zero_reference_reason': None, 'source_files': {}}


def reference(identifier, path):
    return {'id': identifier, 'role': 'identity', 'source': {'kind': 'supplied-file',
        'reference_id': identifier, 'resolved_path': path},
        'subject_uses': [{'subject_id': 'A', 'use': 'identity', 'priority': 0}]}


class ChoiceOwnerTests(unittest.TestCase):
    def setUp(self):
        task, _ = candidate()
        self.choices = inputs.draft_choices(task)

    def edit(self, pointer, *value, **kwargs):
        return edits.apply_edit(self.choices, pointer, *value, file='draft/choices.json', **kwargs)

    def test_add_replace_remove_arrays_and_escaped_object_members(self):
        self.choices = self.edit('/authoring/task/criteria/-',
            {'id': 'output', 'text': None, 'strength': 'hard', 'evidence': 'text'}, operation='add')
        self.choices = self.edit('/authoring/task/criteria/0/text', 'Compare the actual authored text.')
        self.assertEqual(self.choices['authoring']['task']['criteria'][0]['text'],
            'Compare the actual authored text.')
        self.choices = self.edit('/authoring/generation/continuity', {}, operation='add')
        self.choices = self.edit('/authoring/generation/continuity/A~1B~0C', 'undecided', operation='add')
        self.assertEqual(self.choices['authoring']['generation']['continuity'], {'A/B~C': 'undecided'})
        removed = self.edit('/authoring/task/criteria/0', operation='remove')
        self.assertEqual(removed['authoring']['task']['criteria'], [])
        self.assertEqual(len(self.choices['authoring']['task']['criteria']), 1)

    def test_partial_judgments_remain_editable_and_wrong_container_types_fail(self):
        self.choices = self.edit('/authoring/task/direction/purpose', None)
        self.choices = self.edit('/authoring/task/criteria', [])
        self.assertIsNone(self.choices['authoring']['task']['direction']['purpose'])
        for pointer, value in [('/authoring/task/criteria', 'not an array'),
                ('/authoring/task/direction', []), ('/authoring/task/recording', 'not an object')]:
            with self.subTest(pointer=pointer), self.assertRaises(ProductionError):
                self.edit(pointer, value, operation='add')

    def test_mixed_parents_generated_fields_and_task_envelopes_cannot_be_edited(self):
        before = copy.deepcopy(self.choices)
        for pointer in ['', '/authoring', '/authoring/task', '/task_changes',
                '/authoring/task/sources', '/authoring/task/task_id', '/authoring/task/authority',
                '/authoring/task/delivery', '/authoring/source_files', '/authoring_stage']:
            with self.subTest(pointer=pointer), self.assertRaises(ProductionError) as raised:
                self.edit(pointer, {}, operation='add')
            self.assertEqual(raised.exception.diagnostic.details['cause'], 'choice-owner-protected')
        self.assertEqual(self.choices, before)

    def test_parent_replacement_retains_measurements_and_rejects_injected_bindings(self):
        refs = reference_choices([reference('first', 'first.png')])
        refs['source_files'] = {'first.png': {'sha256': '1' * 64, 'media_type': 'image/png'}}
        self.choices['authoring']['references'] = refs
        selected = reference_choices([reference('second', 'second.png')])
        selected.pop('source_files')
        result = self.edit('/authoring/references', selected)
        self.assertEqual(result['authoring']['references']['source_files'], refs['source_files'])
        cases = [
            ('/authoring/references', {**selected, 'source_files': {}}),
            ('/authoring/references/image_input', {'references': [], 'binding_sha256': '2' * 64}),
            ('/authoring/references/additional_references', [
                {**reference('third', 'third.png'), 'source': {
                    **reference('third', 'third.png')['source'], 'sha256': '3' * 64}}]),
        ]
        for pointer, value in cases:
            with self.subTest(pointer=pointer), self.assertRaises(ProductionError) as raised:
                self.edit(pointer, value)
            self.assertEqual(raised.exception.diagnostic.details['cause'], 'choice-owner-protected')

    def test_reference_reorder_keeps_stable_source_selections(self):
        rows = [reference('first', 'first.png'), reference('second', 'second.png')]
        self.choices['authoring']['references'] = reference_choices(rows)
        result = self.edit('/authoring/references/additional_references', list(reversed(rows)))
        self.assertEqual(result['authoring']['references']['additional_references'], list(reversed(rows)))
        self.assertEqual(self.choices['authoring']['references']['additional_references'], rows)

    def test_retained_visual_measurement_reaches_its_validator_and_cannot_be_edited(self):
        self.choices['visual'] = {'purpose': None,
            'basis': {'path': 'basis.txt', 'locator': 'whole document', 'sha256': 'a' * 64},
            'subjects': None, 'production_spec': None, 'prepared_reference_set': None}
        # Existing evidence reaches the visual-continuity owner, which can
        # identify an invalid source witness without a generic schema error.
        inputs._validate_choices(self.choices)
        for pointer, value in [('/visual/basis/sha256', 'b' * 64),
                ('/visual/basis', {'path': 'basis.txt', 'locator': 'whole document', 'sha256': 'b' * 64})]:
            with self.subTest(pointer=pointer), self.assertRaises(ProductionError) as raised:
                self.edit(pointer, value)
            self.assertEqual(raised.exception.diagnostic.details['cause'], 'choice-owner-protected')
        selected = self.edit('/visual/basis', {'path': 'actual-basis.txt', 'locator': 'whole document'})
        self.assertEqual(selected['visual']['basis'], {'path': 'actual-basis.txt', 'locator': 'whole document'})

    def test_selected_document_content_has_one_owner(self):
        self.choices['authoring']['delivery'] = {'file': 'prompt.json', 'field': ['text'], 'translation_notes': None}
        self.choices['authoring']['documents'] = {'parameters': {'file': 'parameters.json'}}
        with self.assertRaises(ProductionError) as raised:
            self.edit('/authoring/delivery/content', 'Unselected duplicate.', operation='add')
        self.assertEqual(raised.exception.diagnostic.details['repair_owner'],
            {'file': 'prompt.json', 'pointer': '/text'})
        with self.assertRaises(ProductionError):
            self.edit('/authoring/documents/parameters/steps', 20, operation='add')
        selected = self.edit('/authoring/documents/parameters/file', 'revised-parameters.json')
        self.assertEqual(selected['authoring']['documents']['parameters'], {'file': 'revised-parameters.json'})

    def test_effective_task_changes_are_normalized_before_new_edit(self):
        self.choices['task_changes'] = {'criteria': [{'id': 'current', 'text': 'Existing current criterion.',
            'strength': 'hard', 'evidence': 'text'}], 'direction': {
                **self.choices['authoring']['task']['direction'], 'purpose': 'Previous effective purpose.'}}
        result = self.edit('/authoring/task/direction/purpose', 'Current edited purpose.')
        self.assertEqual(result['task_changes'], {})
        self.assertEqual(result['authoring']['task']['criteria'][0]['id'], 'current')
        self.assertEqual(result['authoring']['task']['direction']['purpose'], 'Current edited purpose.')

    def test_native_request_controls_are_editable_and_derived_values_remain_with_their_owners(self):
        self.choices['external'] = {'image_input': {'references': [], 'external_request': {
            'prompt_field': ['prompt'], 'model_field': ['model'], 'count_field': ['count'], 'count': 1}},
            'request': {'prompt': None, 'model': None, 'count': None, 'steps': 12},
            'media_slots': [], 'source_files': {}, 'source_uploads': [], 'reference_delivery': None}
        selected = self.edit('/external/request/steps', 18)
        self.assertEqual(selected['external']['request']['steps'], 18)
        # A provider's independent property named sha256 is not a generated
        # Production measurement merely because it shares that spelling.
        selected = self.edit('/external/request/sha256', 'native-value', operation='add')
        self.assertEqual(selected['external']['request']['sha256'], 'native-value')
        for pointer, value in [('/external/request/prompt', 'A duplicate prompt.'),
                ('/external/request', {'prompt': 'A duplicate prompt.', 'steps': 18}),
                ('/external/image_input', {'references': [], 'external_request': {'file': 'request.json'}})]:
            with self.subTest(pointer=pointer), self.assertRaises(ProductionError) as raised:
                self.edit(pointer, value)
            self.assertEqual(raised.exception.diagnostic.details['cause'], 'choice-owner-protected')

    def test_parent_reference_array_cannot_inject_attachment_positions(self):
        self.choices['authoring']['references'] = reference_choices()
        self.choices['authoring']['references']['image_input'] = {'references': []}
        with self.assertRaises(ProductionError) as raised:
            self.edit('/authoring/references/image_input/references', [{'id': 'first',
                'file': 'first.png', 'role': 'identity', 'attachment_number': 7}])
        self.assertEqual(raised.exception.diagnostic.details['cause'], 'choice-field-unknown')
        self.assertTrue(raised.exception.diagnostic.pointer.endswith('/attachment_number'))

    def test_invalid_pointer_operation_or_value_cannot_modify_the_candidate(self):
        before = copy.deepcopy(self.choices)
        for pointer in ['/authoring/task/criteria/00', '/authoring/task/criteria/2',
                '/authoring/task/direction/~2bad', '/authoring/task/direction/absent/child']:
            with self.subTest(pointer=pointer), self.assertRaises(ProductionError):
                self.edit(pointer, {}, operation='add')
        with self.assertRaises(ProductionError):
            self.edit('/authoring/task/criteria', operation='replace')
        with self.assertRaises(ProductionError):
            self.edit('/authoring/task/criteria', [], operation='remove')
        self.assertEqual(self.choices, before)

    def test_received_pointer_survives_diagnostics_and_names_git_bash_repair(self):
        before = copy.deepcopy(self.choices)
        for pointer in ['C:/Program Files/Git/authoring/task/criteria',
                '/C:/Program Files/Git/authoring/task/criteria', '/authoring/task/~2bad']:
            with self.subTest(pointer=pointer), self.assertRaises(ProductionError) as raised:
                self.edit(pointer, [], operation='add')
            diagnostic = raised.exception.diagnostic.as_dict()
            self.assertEqual(diagnostic['pointer'], pointer)
            self.assertEqual(diagnostic['received_pointer'], pointer)
            self.assertIn('MSYS_NO_PATHCONV=1', diagnostic['required_action'])
            self.assertEqual(diagnostic['repair_owner']['file'], 'draft/choices.json')
        self.assertEqual(self.choices, before)


class PublishedChoiceEditTests(unittest.TestCase):
    save_choices = fixtures.InputToolsTests.save_choices
    files = fixtures.InputToolsTests.files

    def setUp(self):
        fixtures.InputToolsTests.setUp(self)

    def value(self, value, name='edit-value.json'):
        (self.root / name).write_bytes(c.encoded(value))
        return name

    def test_public_cli_edits_current_partial_choices_and_inspection_reads_the_result(self):
        value_file = self.value('Review the revised local text.')
        command = [sys.executable, str(inputs.ROOT / 'scripts/production_workflow.py'),
            'edit-choices', '--root', str(self.root), '--choices', self.choices_path,
            '--pointer', '/authoring/task/criteria/0/text', '--value-file', value_file]
        completed = subprocess.run(command, cwd=self.root, capture_output=True, text=True,
            encoding='utf-8', timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report['ok'])
        difference = next(row for row in report['edit']['changes']
            if row['pointer'] == '/authoring/task/criteria')
        self.assertEqual(difference['after'][0]['text'], 'Review the revised local text.')
        current = c.load(self.root / self.choices_path)
        self.assertEqual(current['authoring']['task']['criteria'][0]['text'], 'Review the revised local text.')
        from input_evidence import InputEvidence
        resolved, _, _, _, _ = inputs._load_editable(self.root, self.choices_path, InputEvidence(self.root), register=False)
        self.assertEqual(inputs._chosen_task(self.task, resolved)['criteria'][0]['text'],
            'Review the revised local text.')
        before = self.files()
        again = edits.edit_choices(self.root, self.choices_path, '/authoring/task/criteria/0/text', value_file=value_file)
        self.assertFalse(again['changed'])
        self.assertEqual(before, self.files())

    def test_rejected_owner_edit_keeps_all_active_files_and_state(self):
        value_file = self.value({'replacement': 'Not an authored envelope.'})
        before = self.files()
        with self.assertRaises(ProductionError):
            edits.edit_choices(self.root, self.choices_path, '/authoring', value_file=value_file)
        self.assertEqual(before, self.files())

    def test_two_process_edits_share_one_choice_and_basis_lock_without_lost_updates(self):
        changes = [('purpose', '/authoring/task/direction/purpose', 'Concurrent purpose.'),
            ('criterion', '/authoring/task/criteria/0/text', 'Concurrent criterion.')]
        processes = []
        try:
            for name, pointer, value in changes:
                value_file = self.value(value, name + '.json')
                processes.append(subprocess.Popen([sys.executable,
                    str(inputs.ROOT / 'scripts/production_workflow.py'), 'edit-choices', '--root', str(self.root),
                    '--choices', self.choices_path, '--pointer', pointer, '--value-file', value_file],
                    cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8'))
            for process in processes:
                stdout, stderr = process.communicate(timeout=60)
                self.assertEqual(process.returncode, 0, stdout + stderr)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        current = c.load(self.root / self.choices_path)['authoring']['task']
        self.assertEqual(current['direction']['purpose'], 'Concurrent purpose.')
        self.assertEqual(current['criteria'][0]['text'], 'Concurrent criterion.')


class CanonicalExternalChoiceTests(unittest.TestCase):
    def test_actual_canonical_external_draft_keeps_source_and_transport_owners(self):
        from production_external_inputs_smoke_test import ExternalInputTests
        import production_external_inputs as external
        import production_target
        fixture = ExternalInputTests('test_prepared_multi_image_retains_canonical_source_and_separate_external_target')
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        prepared = fixture.prepared_fixture('multi-image')
        task = c.load(fixture.root / 'task.json')
        choices = inputs.draft_choices(task)
        choices['external'] = external.draft(fixture.plan, fixture.request,
            prepared=prepared, package_root=fixture.root, root=fixture.root)
        choices['target'] = production_target.extract(task, choices['authoring'], choices['external'])
        inputs._validate_choices(choices)
        selected = edits.apply_edit(choices, '/external/reference_delivery/choices/max_side', 64)
        self.assertEqual(selected['external']['reference_delivery']['choices']['max_side'], 64)
        self.assertEqual(selected['external']['reference_delivery']['choices']['additional_references'],
            choices['external']['reference_delivery']['choices']['additional_references'])
        self.assertEqual(selected['external']['image_input'], choices['external']['image_input'])


class RefusedReferenceEditTests(unittest.TestCase):
    files = fixtures.InputToolsTests.files

    def setUp(self):
        from test_production_identity import IdentityAuthoringTests
        IdentityAuthoringTests.setUp(self)
        result, choices = IdentityAuthoringTests.draft_identity(self)
        self.choices_path = result['choices_file']
        self.choices = choices
        (self.root / self.choices_path).write_bytes(c.encoded(choices))

    def test_array_add_assigns_a_stable_reference_before_identity_comparison(self):
        from reference_runtime_smoke_test import _fixture_png
        self.choices['authoring']['references'] = reference_choices()
        (self.root / self.choices_path).write_bytes(c.encoded(self.choices))
        (self.root / 'added.png').write_bytes(_fixture_png())
        row = reference('unused', 'added.png')
        row.pop('id')
        row['source'].pop('reference_id')
        (self.root / 'new-row.json').write_bytes(c.encoded(row))
        with self.assertRaises(ProductionError) as raised:
            edits.edit_choices(self.root, self.choices_path,
                '/authoring/references/additional_references/-', operation='add', value_file='new-row.json')
        problem = raised.exception.diagnostic.as_dict()
        self.assertEqual(problem['code'], 'IDENTITY_SOURCE_CHANGED')
        proposal = c.load(self.root / problem['proposed_candidate']['choices'])
        captured = proposal['authoring']['references']['additional_references'][0]
        self.assertTrue(captured['id'].startswith('reference-'))
        self.assertEqual(captured['source']['reference_id'], captured['id'])
        self.assertIn('reference:' + captured['id'], {row['source'] for row in problem['changes']})
        self.assertEqual(c.load(self.root / self.choices_path)['authoring']['references']['additional_references'], [])

    def test_identity_reference_addition_keeps_original_and_repair_carries_actual_unapplied_content(self):
        from reference_runtime_smoke_test import _fixture_png
        proposed_bytes = _fixture_png()
        (self.root / 'new-reference.png').write_bytes(proposed_bytes)
        selected = reference_choices([reference('new-reference', 'new-reference.png')])
        (self.root / 'selected-reference.json').write_bytes(c.encoded(selected))
        before = self.files()
        with self.assertRaises(ProductionError) as raised:
            edits.edit_choices(self.root, self.choices_path, '/authoring/references',
                value_file='selected-reference.json')
        problem = raised.exception.diagnostic.as_dict()
        self.assertEqual(problem['code'], 'IDENTITY_SOURCE_CHANGED')
        self.assertIn('added', {row['change_kind'] for row in problem['changes']})
        after = self.files()
        for path, raw in before.items():
            self.assertEqual(after[path], raw, path)
        self.assertEqual(c.load(self.root / self.choices_path)['authoring']['references'],
            self.choices['authoring']['references'])
        proposal = problem['proposed_candidate']['choices']
        self.assertIn(proposal, problem['repair_action']['argv'])
        (self.root / 'selected-reference.json').unlink()
        (self.root / 'new-reference.png').unlink()
        completed = subprocess.run(problem['repair_action']['argv'], cwd=self.root,
            capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        argv = problem['repair_action']['argv']
        folder = argv[argv.index('--out-dir') + 1]
        restored = c.load(self.root / folder / 'choices.json')
        row = restored['authoring']['references']['additional_references'][0]
        self.assertEqual(row['id'], 'new-reference')
        self.assertEqual((self.root / row['source']['resolved_path']).read_bytes(), proposed_bytes)
        self.assertEqual(c.load(self.root / folder / 'work-basis.json')['operation'], 'compose')


class PublicationWitnessTests(unittest.TestCase):
    save_choices = fixtures.InputToolsTests.save_choices
    files = fixtures.InputToolsTests.files

    def setUp(self):
        from test_production_source_acquisition import SourceAcquisitionTests
        SourceAcquisitionTests.setUp(self)

    def test_absolute_reference_change_after_boundary_check_keeps_original_draft(self):
        import production_identity_boundary as boundary
        from reference_runtime_smoke_test import _fixture_png
        temporary = tempfile.TemporaryDirectory(prefix='cpb-edit-absolute-source-')
        self.addCleanup(temporary.cleanup)
        image = Path(temporary.name) / 'source.png'
        image.write_bytes(_fixture_png())
        self.choices['authoring']['references'] = reference_choices([reference('selected', str(image))])
        self.save_choices()
        (self.root / 'purpose.json').write_bytes(c.encoded('A revised local purpose.'))
        before = self.files()
        require_unchanged = boundary.require_unchanged
        compared = []

        def replace_after_comparison(context, basis, proposed, **kwargs):
            require_unchanged(context, basis, proposed, **kwargs)
            compared.append(proposed)
            image.write_bytes(b'Changed absolute source after the acquired comparison.')

        with patch.object(boundary, 'require_unchanged', side_effect=replace_after_comparison):
            with self.assertRaises(ProductionError) as raised:
                edits.edit_choices(self.root, self.choices_path,
                    '/authoring/task/direction/purpose', value_file='purpose.json')
        problem = raised.exception.diagnostic.as_dict()
        self.assertEqual(problem['cause'], 'authoring-source-changed')
        self.assertEqual(problem['file'], str(image))
        self.assertEqual(len(compared), 1)
        self.assertIn('reference:selected', {row['id'] for row in compared[0]['sources']})
        self.assertEqual(self.files(), before)


class ChoiceEditArgumentsTests(unittest.TestCase):
    def parser(self):
        import production_workflow
        return production_workflow.build_parser()

    def test_minimal_public_constructor_and_editor_arguments(self):
        parser = self.parser()
        selected = parser.parse_args(['draft-inputs', '--root', '/studio',
            '--choices', 'proposal/choices.json', '--out-dir', 'new-compose'])
        self.assertEqual(selected.choices, 'proposal/choices.json')
        self.assertIsNone(selected.operation)
        patch = parser.parse_args(['edit-choices', '--root', '/studio', '--choices', 'draft/choices.json',
            '--pointer', '/authoring/task/criteria/0', '--operation', 'remove'])
        self.assertIsNone(patch.value_file)
        self.assertFalse(hasattr(patch, 'run'))
        commands = next(action for action in parser._actions if action.dest == 'command').choices
        options = {option for action in commands['draft-inputs']._actions for option in action.option_strings}
        self.assertFalse(options & {'--reuse-content', '--from-choices', '--edit-pointer', '--edit-operation',
            '--edit-value-file', '--expect-edit-base'})


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
