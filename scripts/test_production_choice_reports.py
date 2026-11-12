"""Each unanswered authored choice tells the agent what to answer and how.

A synthetic draft leaves one choice unanswered at a time. `prepare --choices`
reports it as AUTHORED_CHOICE_REQUIRED with its reason, field, message, repair
and an existing guidance section. `inspect-inputs` and status show the same
entry before preparation, except for the choices that only materializing the
inputs can detect. No provider is contacted.
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

import execution_contract as c
import production_case_fixtures as cases
import production_diagnostics
import production_inputs
import production_inputs_smoke_test as input_fixtures
import production_workflow as workflow
from production_diagnostics import CompilationError, guidance
from validate import markdown_anchor_slugs

ROOT = Path(__file__).resolve().parents[1]
CODE = 'AUTHORED_CHOICE_REQUIRED'


class ChoiceReports:
    """Assertions shared by the synthetic Studios below."""

    def assert_guidance(self, owner: dict) -> None:
        path, _, anchor = owner['document_path'].partition('#')
        self.assertTrue((ROOT / path).is_file(), path)
        self.assertIn(anchor, markdown_anchor_slugs(ROOT / path), owner['document_path'])

    def assert_choice(self, entry: dict, reason: str, field: str, *, named: str | None = None,
                      mentions: tuple[str, ...] = ()) -> None:
        self.assertEqual((entry['code'], entry.get('reason'), entry['field']), (CODE, reason, field), entry)
        self.assertIn(reason, production_diagnostics.CHOICE_REASONS)
        self.assertTrue(entry['message'].strip(), entry)
        location = entry['file'] if 'source_field' in entry else field
        self.assertIn(named or location, entry['required_action'], entry)
        for text in mentions:
            self.assertIn(text, entry['required_action'], entry)
        self.assert_guidance(entry['guidance'])

    def refused(self, choices_path: str) -> dict:
        """The report of `prepare --choices`, which publishes nothing."""
        with self.assertRaises(CompilationError) as caught:
            workflow.prepare(self.root, choices=choices_path)
        report = caught.exception.report
        self.assertFalse(report['publishable'])
        return report

    def diagnostic(self, diagnostics: list[dict], reason: str, field: str) -> dict:
        matches = [row for row in diagnostics if row.get('reason') == reason and row['pointer'] == field]
        self.assertEqual(len(matches), 1, diagnostics)
        row = matches[0]
        self.assertEqual((row['severity'], row['phase']), ('error', 'authoring'))
        return row

    def inspected(self, choices_path: str) -> list[dict]:
        """The unanswered entries of inspect-inputs and of status for one registered draft."""
        state = production_inputs.inspect_inputs(self.root, choices_path=choices_path)
        row = next(item for item in state['inputs'] if item['current'])
        entries = row.get('working_copy', row)['unresolved']
        status = workflow.status(self.root)
        workflow.schema_check(status, 'status')
        current = next(item for item in status['current_task']['authoring']['inputs'] if item['current'])
        self.assertEqual(current.get('working_copy', current)['unresolved'], entries)
        self.assertEqual(status['current_task']['authoring']['context']['input']['unresolved'], entries)
        return entries

    def assert_reported(self, choices_path: str, expected: list[tuple], *, inspect: bool = True) -> dict:
        """Each (reason, field, options) appears in prepare and, when detectable, in inspect-inputs."""
        report = self.refused(choices_path)
        entries = self.inspected(choices_path) if inspect else []
        found = {}
        for reason, field, options in expected:
            with self.subTest(reason=reason, field=field):
                row = found[reason, field] = self.diagnostic(report['diagnostics'], reason, field)
                self.assert_choice(row, reason, field, **options)
                if inspect:
                    same = [item for item in entries if item['field'] == field and item.get('reason') == reason]
                    self.assertEqual(len(same), 1, entries)
                    for key in ('code', 'message', 'required_action', 'guidance'):
                        self.assertEqual(same[0][key], row[key], key)
        workflow.schema_check(report, 'compilation-report')
        return found


class AuthoredChoiceReportTests(ChoiceReports, unittest.TestCase):
    """A text task and an external task drafted from nothing, then edited one choice at a time."""

    setUp = input_fixtures.InputToolsTests.setUp
    save_choices = input_fixtures.InputToolsTests.save_choices
    prepared_source = input_fixtures.InputToolsTests.prepared_source
    external_choice = input_fixtures.InputToolsTests.external_choice

    def begin(self) -> None:
        import work_ledger
        self.task['task_id'] = work_ledger.begin(self.root, 'Answer the synthetic choices.', ['Compose'])['task_id']

    def initial(self, directory: str, **options) -> tuple[dict, dict]:
        self.begin()
        result = production_inputs.draft_inputs(self.root, None, directory, route='development', **options)
        return result, c.load(self.root / result['choices_file'])

    def write(self, result: dict, choices: dict) -> str:
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        return result['choices_file']

    def test_unread_route_names_its_read_command_and_the_key_to_select(self):
        result, choices = self.initial('draft')
        reading = next(row for row in result['unresolved'] if row['field'] == 'reading.reading_key')
        self.assert_choice(reading, 'reading-required', 'reading.reading_key',
                           mentions=('execution_routes.py', 'read development', 'actions.continue', 'reading.key'))
        self.assertEqual(reading['next_action']['positional'], ['development'])
        self.assertEqual(reading['next_actions'], [reading['next_action']])
        self.assert_reported(result['choices_file'], [
            ('reading-required', 'reading.reading_key', {'mentions': ('execution_routes.py', 'reading.key')})])
        choices['reading'] = None
        self.assert_reported(self.write(result, choices), [
            ('reading-required', 'reading', {'mentions': ('execution_routes.py', '"reading_key"')})])

    def test_empty_commission_fields_name_what_to_write_and_where(self):
        result, choices = self.initial('draft')
        choices['reading'] = copy.deepcopy(self.choices['reading'])
        self.assert_reported(self.write(result, choices), [
            ('authored-choice-required', 'authoring.task.direction.purpose', {}),
            ('authored-choice-required', 'authoring.task.direction.intended_effect', {}),
            ('authored-choice-required', 'authoring.task.criteria', {'mentions': ('"strength"', '"evidence"')}),
            ('authored-choice-required', 'authoring.delivery.content', {'mentions': ('authoring.delivery.file',)})])

    def test_visual_choices_name_each_missing_selection(self):
        result, choices = self.initial('draft')
        choices['reading'] = copy.deepcopy(self.choices['reading'])
        choices['visual'] = {'purpose': None, 'basis': {'path': None, 'locator': 'Decision record.'},
                             'subjects': {'person': {'continuity': None, 'character_id': None,
                                                     'studio_character': None, 'identity_refs': []}},
                             'production_spec': 'spec.json', 'prepared_reference_set': 'prepared.json'}
        self.assert_reported(self.write(result, choices), [
            ('selection-required', 'visual.purpose', {'mentions': ('"image"', '"sheet-panel"')}),
            ('source-selection-required', 'visual.basis.path', {}),
            ('continuity-choice-required', 'visual.subjects.person.continuity',
             {'mentions': ('"undecided"', '"recurring"', '"one-off"')})])

    def test_external_draft_names_target_plan_and_request(self):
        result, choices = self.initial('external', artifact='image', execution='external')
        self.assert_reported(result['choices_file'], [
            ('target-selection-required', 'target', {'mentions': ('render_contract.py models',)}),
            ('selection-required', 'external.image_input', {}),
            ('selection-required', 'external.request', {})])
        choices['external'] = {'image_input': 'inputs/missing-plan.json'}
        self.assert_reported(self.write(result, choices), [
            ('selection-evidence-required', 'external.image_input', {})])

    def test_changed_upload_value_names_the_upload_to_select(self):
        _, draft, _, _ = self.external_choice(with_reference=True)
        choices = c.load(self.root / draft['choices_file'])
        choices['external']['image_input']['references'][0]['transport']['value'] = 'another-media-token'
        (self.root / draft['choices_file']).write_bytes(c.encoded(choices))
        field = 'external.image_input.references.surface-sample.transport'
        found = self.assert_reported(draft['choices_file'], [
            ('provider-upload-required', field,
             {'named': 'external.image_input.references', 'mentions': ('"surface-sample"', 'sample.png')})],
            inspect=False)
        self.assertEqual(found['provider-upload-required', field]['carrier']['path'], 'sample.png')

    def test_cli_prepare_prints_the_choice_report_and_exits_two(self):
        import production_fixtures
        result, _ = self.initial('cli-draft')
        home = production_fixtures.scratch_home_dir(self.root.parent / (self.root.name + '-home'))
        run = subprocess.run([sys.executable, str(ROOT / 'scripts/production_workflow.py'), 'prepare',
                              '--root', str(self.root), '--choices', result['choices_file']],
                             env={**os.environ, 'CPB_HOME': str(home)}, capture_output=True, text=True,
                             encoding='utf-8', check=False)
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        report = json.loads(run.stdout)
        found = self.diagnostic(report['diagnostics'], 'reading-required', 'reading.reading_key')
        self.assert_choice(found, 'reading-required', 'reading.reading_key', mentions=('execution_routes.py',))

    def test_authoring_phase_names_the_section_on_editable_choices(self):
        owner = guidance('authoring')
        self.assertIsNotNone(owner)
        self.assert_guidance(owner)


class DispatcherChoiceReportTests(ChoiceReports, unittest.TestCase):
    """A complete synthetic image task whose draft is edited one choice at a time."""

    def setUp(self):
        import production_case_fixtures as cases
        import production_fixtures
        from catalog_retrieval import runtime
        temporary = tempfile.TemporaryDirectory(prefix='cpb-choice-reports-')
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.enterContext(production_fixtures.scratch_home(base / 'home'))
        self.case = cases.create(base / 'studio', base / 'runtime', with_upscale=True)
        self.root = self.case['root']
        self.addCleanup(runtime.configure_pack_runtime, None)

    def draft(self, task: str = 'task.json', directory: str = 'draft') -> tuple[dict, dict]:
        result = production_inputs.draft_inputs(self.root, task, directory)
        self.assertEqual(result['unresolved'], [])
        return result, c.load(self.root / result['choices_file'])

    def write(self, result: dict, choices: dict) -> str:
        (self.root / result['choices_file']).write_bytes(c.encoded(choices))
        return result['choices_file']

    def test_target_choices_name_the_listing_and_the_value(self):
        result, choices = self.draft()
        choices['target']['service'] = None
        self.assert_reported(self.write(result, choices), [
            ('target-selection-required', 'target.service', {'mentions': ('catalog_cli.py inspect', 'record.offerings')})])
        choices['target'] = {'kind': 'catalog', 'model': 'not-a-fixture-model', 'service': 'synthetic'}
        found = self.assert_reported(self.write(result, choices), [
            ('target-evidence-required', 'target', {'mentions': ('render_contract.py model',)})])
        self.assertIn('not-a-fixture-model', found['target-evidence-required', 'target']['message'])

    def test_plot_without_approval_names_the_approval_to_record(self):
        result, choices = self.draft()
        with cases.edit_document(self.root, choices, 'plot') as document:
            document['approved'] = None
        self.assert_reported(self.write(result, choices), [
            ('plot-approval-required', 'authoring.documents.plot.approved', {'mentions': ('"by"', '"at"')})])

    def test_changed_plot_under_its_earlier_approval_asks_for_current_judgment(self):
        result, choices = self.draft()
        with cases.edit_document(self.root, choices, 'plot') as document:
            document['story'][0]['beat'] = 'The synthetic robot turns toward the viewer.'
        self.assert_reported(self.write(result, choices), [
            ('current-judgment-required', 'authoring.documents.plot.approved', {'mentions': ('"by"', '"at"')})],
            inspect=False)

    def test_initial_image_draft_names_its_model_and_rendering_operation(self):
        result = production_inputs.draft_inputs(self.root, None, 'initial', route='generation',
                                                artifact='image', execution='dispatcher')
        self.assert_reported(result['choices_file'], [
            ('target-selection-required', 'target.model', {'mentions': ('render_contract.py models',)}),
            ('target-selection-required', 'target.service', {'mentions': ('catalog_cli.py inspect', 'record.offerings')}),
            ('authored-choice-required', 'authoring.generation.render_intent',
             {'mentions': ('"execution_mode"', 'render_contract.py intent')})])

    def test_validation_choices_name_their_mode_and_sources(self):
        import production_case_fixtures as cases
        source = cases.upscale_task(self.root)
        result, choices = self.draft(source, 'upscale/draft')
        choices['validation'] = None
        self.assert_reported(self.write(result, choices), [
            ('selection-required', 'validation', {'mentions': ('"target-schema"',)})])
        choices['validation'] = {'mode': 'bounded-probe', 'contract': None, 'evidence': None, 'execution_policy': None}
        self.assert_reported(self.write(result, choices), [
            ('source-selection-required', 'validation.contract', {}),
            ('source-selection-required', 'validation.evidence', {})])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
