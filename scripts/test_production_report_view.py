"""Bound display growth while retaining complete operation results and meaning."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
from owned_json import freeze
import production_permissions as permissions
from production_read_model import RunView
import production_report_view as views
import production_status_view


def grant(identifier, *, operations=None, targets=None):
    return {'id': identifier, 'actor': 'Synthetic actor', 'mode': 'direct',
            'operations': operations or ['direction'], 'targets': targets or ['purpose', 'decision:color'],
            'protected_criteria': [], 'expires_at': None, 'request_scope': None,
            'submission_validation_modes': []}


def authority(grants):
    return {'task_id': 'synthetic-task', 'issuer': 'Synthetic issuer',
            'evidence': {'path': 'instruction.txt', 'locator': 'whole'},
            'grants': grants, 'stop_conditions': []}


def requirements(grants, *, selected=None):
    return permissions.grant_requirements(authority(grants),
        [{'operation': 'direction', 'targets': ['purpose', 'decision:color']}],
        selections=[{'operation': 'direction', 'grant': selected}] if selected else None)


def status(requirements_value, document=None):
    return {'ok': True, 'current_task': None, 'runs': [{
        'run': 'synthetic-run', 'task_id': 'synthetic-task', 'integrity': 'intact',
        'readiness': 'authorization_required', 'submission': 'unclaimed',
        'capture': 'none', 'registration': 'unregistered', 'task_disposition': 'open',
        'readiness_diagnostics': [], 'next_action': {'command': 'draft-execution',
            'argv': ['python', 'production_workflow.py', 'draft-execution', '--run', 'synthetic-run'],
            'reason': 'Complete the actual decisions.'},
        'authority': {'document': document, 'event_sha256': 'a' * 64, 'source_path': 'authority.json'},
        'authorization_requirements': requirements_value, 'candidate_states': []}],
        'diagnostics': [], 'external_effect': False, 'execution_records': {
            'complete': True, 'diagnostics': [], 'submissions': 0, 'captured_outputs': 0,
            'reported_cost': {}, 'usage_complete': True, 'executions': []},
        'staging': [], 'staging_details': [], 'unclaimed_journals': [], 'unregistered_publications': []}


def long_authoring_status():
    """A synthetic long-lived task with many branches, decisions and readings."""
    read = {'command': 'read', 'argv': ['python', '/skill/scripts/execution_routes.py', 'read',
            'generation', '--operation', 'prepare', '--execution', 'dispatcher'],
            'reason': 'Read the applicable current source bodies.'}
    changes = [{'kind': 'document', 'path': f'references/runtime/changed-source-{number:03d}.md',
                'change': 'modified', 'before': 'a' * 64, 'after': 'b' * 64} for number in range(80)]
    issue = {'field': 'reading.reading_key', 'code': 'TARGET_GUIDANCE_REQUIRED',
        'message': 'reading sources changed: ' + ', '.join(row['path'] for row in changes),
        'required_action': 'Read the applicable current guidance and select its issued reading key.',
        'source_changes': {'code': 'READING_SOURCES_CHANGED', 'changes': changes, 'actions': {'restart': read}},
        'next_action': read, 'next_actions': [read]}
    inputs = [{'state': 'choices', 'kind': 'draft-inputs', 'directory': f'work/branch-{number:03d}',
        'choices': f'work/branch-{number:03d}/choices.json', 'source_run': 'synthetic-run',
        'current': number == 63, 'unresolved': [copy.deepcopy(issue)], 'next_actions': [copy.deepcopy(read)]}
        for number in range(64)]
    draft_rows = [{'kind': 'review', 'run': 'synthetic-run' if number < 12 else 'unrelated-run',
        'path': f'work/decisions/{number:03d}.json', 'available': True, 'created_at': f'2026-01-{number:03d}',
        'relation': 'selected-run' if number < 12 else 'task-history'} for number in range(72)]
    report = status(None)
    report['current_task'] = {'task_id': 'synthetic-task', 'goal': 'Continue the current synthetic commission.',
        'production_run': 'synthetic-run', 'focus': 'authoring', 'next_actions': [copy.deepcopy(read)],
        'authoring': {'state': 'authoring-state', 'task_id': 'synthetic-task', 'pending': True,
            'selection_required': False, 'external_effect': False, 'diagnostics': [],
            'inputs': inputs, 'decision_drafts': draft_rows, 'last_check': None,
            'input_options': [{'choices': row['choices'], 'directory': row['directory'],
                'source_run': row['source_run'], 'action': copy.deepcopy(read), 'unresolved': [copy.deepcopy(issue)]}
                for row in inputs],
            'readings': [{'state': 'partial', 'route': 'generation', 'operation': 'prepare',
                'execution': 'dispatcher', 'current': True, 'snapshot': str(number),
                'next_actions': [copy.deepcopy(read)], 'remaining_bytes': 500}
                for number in range(64)],
            'next_actions': [copy.deepcopy(read)],
            'context': {'work': {'task_id': 'synthetic-task', 'goal': 'Current synthetic goal: 現在の作業',
                'notes': ['Historical production note.' * 100 for _ in range(80)], 'questions': [],
                'blocked_on': None}, 'input': {'state': 'choices', 'directory': inputs[-1]['directory'],
                'choices_file': inputs[-1]['choices'], 'unresolved': [copy.deepcopy(issue)]}}}}
    return report


def prepared_authoring_status(root):
    """A prepared draft keeps editable files and the former stage navigation."""
    from production_reading_scope import actions
    import production_inputs
    path = 'work/one-character/choices.json'
    runtime = {'state-file': str(root / 'isolated-runtime/pack-state.json'),
        'cache-dir': str(root / 'isolated-runtime/cache'),
        'managed-root': str(root / 'isolated-runtime/packs'),
        'pack-root': str(views.SCRIPT.parents[1] / 'packs/commons')}
    task = {'route': 'generation', 'execution': 'dispatcher',
        'features': ['vocabulary', 'render-contract', 'production-spec', 'reference-delivery']}
    choices = {'authoring_stage': 'prepare', 'target': {'kind': 'catalog',
        'model': 'synthetic-image', 'service': 'synthetic-service'}}
    scope = {'stage': 'prepare', 'composition': 'compose', 'source_formats': ['text'],
        'documents': ['production_spec', 'parameters', 'retrieval_record'],
        'render_operation': 'generation', 'conditions': ['production-spec']}
    read = production_inputs._reading_action(root, task, choices, runtime,
        choices_path=path, authoring_scope=scope)
    stages = actions(root, path, 'prepare', runtime)
    stage = {'stage': 'prepare', 'purpose': 'Bind the saved content to its exact request.',
        'structural_ready': True, 'final_inputs_ready': True, 'unresolved': [], 'pending': [],
        'meaning': 'Structural readiness supplies no artistic judgment or authority.'}
    locations = {name: {'file': 'work/one-character/' + file, 'pointer': None,
        'guidance': {'document_path': 'references/runtime/production-authoring.md#use-the-delivered-knowledge',
                     'schema': 'schemas/authoring/production-input-draft.schema.json'}}
        for name, file in [('authoring.delivery', 'prompt.txt'),
                          ('authoring.documents.parameters', 'parameters.json'),
                          ('authoring.documents.production_spec', 'production-spec.json'),
                          ('authoring.documents.retrieval_record', 'retrieval.json')]}
    row = {'state': 'choices', 'kind': 'draft-inputs', 'directory': 'work/one-character',
        'choices': path, 'current': True, 'prepared_run': 'synthetic-run',
        'source_available': True, 'changed_since_save': False, 'editable_locations': locations,
        'unresolved': [], 'diagnostics': [], 'next_actions': [], 'authoring_stage': stage,
        'fresh_context_action': read, 'stage_actions': stages}
    selected = {'state': 'choices', 'directory': str(root / row['directory']),
        'choices_file': str(root / path), 'prepared_run': row['prepared_run'],
        'changed_since_build': False, 'editable_locations': locations,
        'unresolved': [], 'authoring_stage': stage, 'fresh_context_action': read}
    report = status(requirements([]), authority([]))
    report['current_task'] = {'task_id': 'synthetic-task', 'production_run': 'synthetic-run',
        'focus': 'execution', 'next_actions': [copy.deepcopy(report['runs'][0]['next_action'])],
        'authoring': {'state': 'authoring-state', 'task_id': 'synthetic-task', 'pending': False,
            'selection_required': False, 'external_effect': False, 'inputs': [row],
            'authoring_stage': stage, 'fresh_context_action': read, 'stage_actions': stages,
            'next_actions': [], 'readings': [{'state': 'recorded', 'current': True,
                'route': 'generation', 'operation': 'prepare', 'execution': 'dispatcher',
                'choices': path, 'remaining_bytes': 0, 'next_actions': [], 'fresh_context_action': read}],
            'context': {'work': {'task_id': 'synthetic-task', 'goal': 'Prepare an inspectable image input.',
                'questions': [{'question_id': 'open-a', 'question': 'Retain the current framing?', 'state': 'open'},
                              {'question_id': 'open-b', 'question': 'Which output format is requested?', 'state': 'open'}],
                'blocked_on': 'A separate current prerequisite.'}, 'input': selected}}}
    return report


class ReportViewTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_ineligible_history_changes_counts_without_repeating_individual_diagnostics(self):
        old = [grant(f'old-{index:04d}', operations=['adopt'], targets=['elsewhere']) for index in range(1600)]
        before = status(requirements(old[:12]), authority(old[:12]))
        after = status(requirements(old), authority(old))
        small = production_status_view.summary(self.root, before, run='synthetic-run')
        large = production_status_view.summary(self.root, after, run='synthetic-run')
        need = large['runs'][0]['authorization_requirements']['requirements'][0]
        self.assertEqual(need['missing_targets'], ['decision:color', 'purpose'])
        self.assertEqual(need['ineligible_reasons'], {'operation': 1600, 'targets': 1600})
        self.assertEqual(need['ineligible_grant_count'], 1600)
        self.assertNotIn('candidates', need)
        self.assertNotIn('old-1599', json.dumps(large))
        self.assertLess(abs(len(json.dumps(large)) - len(json.dumps(small))), 100)
        self.assertEqual(large['runs'][0]['next_action'], after['runs'][0]['next_action'])
        self.assertEqual(len(after['runs'][0]['authorization_requirements']['requirements'][0]['candidates']), 1600)

    def test_many_eligible_grants_are_bounded_and_selection_beyond_prefix_stays_explicit(self):
        grants = [grant(f'eligible-{index:04d}') for index in range(1600)]
        original = requirements(grants, selected='eligible-1599')
        complete = copy.deepcopy(original)
        value = views.authorization_requirements(original)['requirements'][0]
        self.assertEqual(len(value['eligible_grants']), 8)
        self.assertEqual(value['eligible_grant_count'], 1600)
        self.assertEqual(value['eligible_grants_omitted'], 1592)
        self.assertEqual(value['selected_grant'], 'eligible-1599')
        self.assertEqual(value['selected_actor'], 'Synthetic actor')
        self.assertTrue(value['eligible'])
        self.assertFalse(value['selection_required'])
        self.assertEqual(original, complete)
        smaller = views.authorization_requirements(requirements(grants[:12], selected='eligible-0011'))
        self.assertLess(abs(len(json.dumps(views.authorization_requirements(original))) - len(json.dumps(smaller))), 100)

    def test_multiple_eligible_grants_remain_an_unanswered_choice(self):
        report = requirements([grant('first'), grant('second')])
        selected = views.authorization_requirements(report)['requirements'][0]
        self.assertFalse(selected['eligible'])
        self.assertTrue(selected['selection_required'])
        self.assertIsNone(selected['selected_grant'])
        self.assertEqual(selected['missing_targets'], [])
        self.assertEqual(selected['diagnostics'][0]['code'], 'AUTHORIZATION_REQUIRED')

    def test_partial_grants_do_not_become_one_eligible_grant(self):
        report = requirements([grant('purpose-only', targets=['purpose']),
                               grant('color-only', targets=['decision:color'])])
        selected = views.authorization_requirements(report)['requirements'][0]
        self.assertFalse(selected['eligible'])
        self.assertEqual(selected['eligible_grant_count'], 0)
        self.assertEqual(selected['missing_targets'], [])
        self.assertEqual(selected['missing_targets_basis'], 'not-covered-by-current-operation-grants')
        self.assertEqual(selected['ineligible_reasons'], {'targets': 2})
        self.assertTrue(selected['diagnostics'])

    def test_selected_partial_grant_keeps_its_exact_missing_targets(self):
        report = requirements([grant('purpose-only', targets=['purpose']), grant('complete')], selected='purpose-only')
        selected = views.authorization_requirements(report)['requirements'][0]
        self.assertFalse(selected['eligible'])
        self.assertEqual(selected['missing_targets'], ['decision:color'])
        self.assertEqual(selected['missing_targets_basis'], 'selected-grant')
        self.assertEqual(selected['eligible_grants'], [{'grant': 'complete', 'actor': 'Synthetic actor'}])

    def test_actor_operation_target_and_lifetime_reasons_use_structured_diagnostics(self):
        report = requirements([grant('wrong', operations=['adopt'], targets=['purpose'])])
        candidate = report['requirements'][0]['candidates'][0]
        candidate['diagnostics'].extend([
            {'code': 'GRANT_SCOPE_EXCEEDED', 'expected': {'actor': 'Required actor', 'operation': 'direction'},
             'actual': {'actor': 'Another actor', 'operations': ['adopt']}},
            {'code': 'GRANT_REVOKED'}, {'code': 'GRANT_NOT_EFFECTIVE'}])
        need = views.authorization_requirements(report)['requirements'][0]
        self.assertEqual(need['ineligible_reasons'],
                         {'actor': 1, 'operation': 1, 'targets': 1, 'revoked-or-expired': 1, 'not-effective': 1})

    def test_failed_projection_keeps_owning_location_and_repair_with_full_snapshot(self):
        repair = {'command': 'acquire-source', 'argv': ['python', 'production_workflow.py', 'acquire-source'],
                  'reason': 'Acquire the original descriptor.'}
        source = {'ok': False, 'diagnostics': [{'code': 'IDENTITY_CONTRACT_INVALID', 'severity': 'error',
            'phase': 'authoring-projection', 'file': 'work/draft/choices.json', 'pointer': '/authoring/task/sources',
            'message': 'The selected identity metadata is absent from its source owner.',
            'cause': 'source-metadata-missing', 'repair_owner': 'work/draft/design-source.json',
            'projection': {'dropped_fields': ['identity'], 'origin_has_source_metadata': False},
            'required_action': 'Acquire the complete Production source row.', 'repair_action': repair,
            'actual': {'inventory': ['retained-entry'] * 600}}], 'request_preview': 'Exact input ' * 900}
        before = copy.deepcopy(source)
        summary = views.present(self.root, source, command='check', choices='work/draft/choices.json')
        self.assertEqual(summary['next_action'], repair)
        problem = summary['diagnostics'][0]
        self.assertEqual(problem['projection'], source['diagnostics'][0]['projection'])
        self.assertEqual(problem['repair_owner'], 'work/draft/design-source.json')
        self.assertEqual(problem['pointer'], '/authoring/task/sources')
        self.assertLess(len(c.encoded(summary)), len(c.encoded(source)))
        self.assertEqual(c.load(self.root / summary['full_report']), before)
        self.assertEqual(source, before)
        viewed = subprocess.run(summary['full_report_action']['argv'], capture_output=True, text=True, encoding='utf-8', check=False)
        self.assertEqual(viewed.returncode, 0, viewed.stderr)
        self.assertEqual(json.loads(viewed.stdout), before)

    def test_snapshots_are_new_content_paths_outside_run_and_event_history(self):
        folder = self.root / 'production/runs/retained'
        folder.mkdir(parents=True)
        (folder / 'prepared.json').write_bytes(b'{"synthetic":"retained"}\n')
        (self.root / 'production/events.jsonl').write_bytes(b'original event evidence\n')
        before = {str(path.relative_to(self.root)): path.read_bytes()
                  for path in (self.root / 'production').rglob('*') if path.is_file()}
        report = {'ok': True, 'task': 'task.json', 'diagnostics': []}
        first = views.present(self.root, report, command='check')
        again = views.present(self.root, report, command='check')
        later = views.present(self.root, {**report, 'ok': False}, command='check')
        self.assertEqual(first['full_report'], again['full_report'])
        self.assertNotEqual(first['full_report'], later['full_report'])
        self.assertTrue(first['full_report'].startswith('work/reports/check/'))
        self.assertEqual(c.digest((self.root / first['full_report']).read_bytes()), first['full_report_sha256'])
        self.assertEqual(before, {str(path.relative_to(self.root)): path.read_bytes()
                                 for path in (self.root / 'production').rglob('*') if path.is_file()})

    def test_display_failure_retains_committed_result_and_complete_evidence_inline(self):
        report = status(None)
        report['external_effect'] = True
        report['execution_completed'] = True
        with patch.object(c, 'atomic', side_effect=OSError('Synthetic report storage failure')):
            result = views.present(self.root, report, command='execute', run='synthetic-run')
        self.assertTrue(result['ok'])
        self.assertTrue(result['execution_completed'])
        self.assertTrue(result['external_effect'])
        self.assertEqual(result['complete_report'], report)
        self.assertIsNone(result['full_report'])
        self.assertIn('does not request another execution', result['report_warning']['required_action'])

    def test_existing_report_damage_is_not_overwritten_or_accepted(self):
        report = {'ok': True, 'diagnostics': []}
        first = views.present(self.root, report, command='check')
        path = self.root / first['full_report']
        path.write_bytes(b'damaged')
        again = views.present(self.root, report, command='check')
        self.assertIsNone(again['full_report'])
        self.assertEqual(again['complete_report'], report)
        self.assertEqual(path.read_bytes(), b'damaged')

    def test_report_publication_does_not_follow_redirected_directory(self):
        target = self.root / 'outside'
        target.mkdir()
        (self.root / 'work').mkdir()
        try:
            (self.root / 'work/reports').symlink_to(target, target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest('This environment cannot create directory symlinks.')
        report = {'ok': True, 'diagnostics': []}
        result = views.present(self.root, report, command='check')
        self.assertIsNone(result['full_report'])
        self.assertEqual(list(target.iterdir()), [])

    def test_shared_and_operation_stop_answers_are_located_without_requiring_both_scope_alternatives(self):
        choices = {'run': 'synthetic-run', 'shared_stop_assessments': [{'id': 'stop', 'clear': False, 'evidence': ''}],
            'decisions': [{'operation': 'direction', 'grant': 'selected', 'reason': 'Actual direction.',
                          'additional_stop_assessments': []},
                         {'operation': 'submit', 'grant': None, 'reason': '', 'additional_stop_assessments': [
                              {'id': 'different', 'clear': False, 'evidence': ''}],
                          'request_decision': {'case': 'actual-case', 'principal_approval': None,
                              'rendition_review': {'assessments': [{'criterion': 'finished-image',
                                  'conclusion': None, 'reason': ''}]}}}]}
        result = views.summarize(self.root, {'choices': choices, 'decisions_file': 'work/decisions.json'},
                                 command='draft-execution')
        pointers = [row['pointer'] for row in result['unresolved']]
        self.assertIn('/shared_stop_assessments/0', pointers)
        self.assertIn('/decisions/1/additional_stop_assessments/0', pointers)
        self.assertIn('/decisions/1/grant', pointers)
        self.assertNotIn('/decisions/1/request_decision/principal_approval', pointers)
        self.assertNotIn('/decisions/1/request_decision', pointers)
        self.assertEqual(result['decisions_file'], 'work/decisions.json')

    def test_authority_import_reports_changes_without_repeating_grant_bodies(self):
        grants = [grant(f'grant-{index:04d}') for index in range(1600)]
        report = {'event': 'authority-updated', 'sequence': 4, 'sha256': 'e' * 64,
            'data': {'authority': authority(grants), 'previous_state': 'd' * 64},
            'changed_grants': {'added': ['new'], 'updated': [], 'revoked': [], 'removed': []}}
        result = views.present(self.root, report, command='authority-import')
        self.assertEqual(result['sequence'], 4)
        self.assertEqual(result['sha256'], 'e' * 64)
        self.assertEqual(result['changed_grants']['added'], {'ids': ['new'], 'total': 1, 'omitted': 0,
            'full_report': result['full_report'] + '#/changed_grants/added'})
        self.assertNotIn('grant-1599', json.dumps(result))
        self.assertEqual(c.load(self.root / result['full_report']), report)

    def test_external_handoff_summary_points_to_exact_request_without_reclaiming(self):
        report = {'artifact_type': 'external-execution-instruction', 'run': 'synthetic-run',
            'state': 'host-call-required', 'external_effect': False,
            'host_request': {'claim': 'a' * 64, 'request': {'prompt': 'An exact synthetic prompt.'}},
            'instruction': 'Invoke this exact host request once and recover the same call after interruption.'}
        result = views.present(self.root, report, command='execute', run='synthetic-run')
        self.assertEqual(result['state'], 'host-call-required')
        self.assertEqual(result['host_request']['claim'], 'a' * 64)
        self.assertEqual(result['next_action']['command'], 'read-report')
        self.assertEqual(c.load(self.root / result['full_report'])['host_request'], report['host_request'])

    def test_source_summary_retains_metadata_locations_and_acquisition_repair(self):
        acquire = {'operation': 'acquire-source', 'argv': ['python', 'production_workflow.py', 'acquire-source'],
                   'source_row_file': 'work/input/source-row.json', 'schema_pointer': '/properties/sources/items'}
        missing = {'required': ['identity-contract'], 'applied': [], 'missing': ['identity-contract'],
                   'source_rows': [{'role': 'identity-contract'}]}
        draft = {'state': 'draft', 'choices_file': 'work/input/choices.json',
            'choices': {'authoring': {'delivery': {'file': 'work/input/prompt.txt'},
                                     'task': {'sources': [{'id': 'source', 'bytes': 'large body'}]}}},
            'authoring_guide': {'schema': 'schema.json', 'source_acquisition': acquire, 'source_requirements': missing},
            'unresolved': [{'field': 'authoring.task.sources', 'message': 'Acquire the required source.',
                            'source_roles': ['identity-contract'], 'repair_action': acquire}],
            'next_actions': []}
        view = views.summarize(self.root, draft, command='draft-inputs')
        self.assertEqual(view['authoring_guide']['source_acquisition'], acquire)
        self.assertEqual(view['authoring_guide']['source_requirements'], missing)
        self.assertEqual(view['unresolved'][0]['source_roles'], ['identity-contract'])
        self.assertEqual(view['editable_locations'], [{'pointer': '/authoring/delivery', 'file': 'work/input/prompt.txt'}])
        self.assertNotIn('choices', view)
        acquired = {'ok': True, 'state': 'source-acquired', 'changed': True, 'source': 'design',
            'source_row': 'work/input/design-source.json', 'choices_file': draft['choices_file'],
            'basis_file': 'work/input/work-basis.json', 'acquired': {'path': 'design.json', 'sha256': 'd' * 64},
            'projected_source': {'id': 'design', 'role': 'identity-contract',
                                 'identity': {'subject_ids': ['A'], 'selectors': ['/identity']}},
            'applications': {'design:1': {'source': 'design', 'pointer': '/identity'}},
            'subjects': {'A': ['design:1']}, 'unresolved': [], 'next_actions': []}
        view = views.summarize(self.root, acquired, command='acquire-source')
        for field in ('source', 'source_row', 'acquired', 'basis_file', 'projected_source', 'applications', 'subjects'):
            self.assertEqual(view[field], acquired[field])

    def test_authority_draft_summary_keeps_unanswered_fields_and_derived_binding(self):
        report = {'state': 'unapproved', 'schema': 'schema.json', 'draft_file': 'work/update.json',
            'expected_event': 'a' * 64, 'unanswered': ['$.grants[0].actor'],
            'required_action': 'Complete actual authority before import.',
            'choices': {'run': 'synthetic-run', 'task_id': 'synthetic-task', 'issuer': 'Synthetic issuer',
                        'expected_event': 'a' * 64,
                        'grants': [{'id': 'direction', 'operation': 'direction', 'targets': ['purpose'],
                                    'actor': None, 'mode': None, 'reason': ''}]}}
        view = views.summarize(self.root, report, command='draft-authority-update')
        self.assertEqual(view['unanswered'], report['unanswered'])
        self.assertEqual(view['draft_file'], 'work/update.json')
        self.assertEqual(view['binding']['issuer'], 'Synthetic issuer')
        self.assertEqual(view['next_action']['command'], 'authority-import')
        self.assertTrue(view['next_action']['requires_author_input'])
        self.assertIsNone(view['grants'][0]['actor'])

    def test_summary_does_not_choose_the_first_editable_branch(self):
        options = [{'command': 'inspect-inputs', 'argv': ['python', '--choices', path], 'reason': 'Inspect this branch.'}
                   for path in ('work/one/choices.json', 'work/two/choices.json')]
        report = {'state': 'authoring-state', 'task_id': 'synthetic-task', 'selection_required': True,
                  'inputs': [], 'next_actions': options, 'input_options': [], 'pending': True}
        view = views.summarize(self.root, report, command='inspect-inputs')
        self.assertEqual(view['next_action']['alternatives'], options)
        self.assertNotIn('--choices', view['next_action']['argv'])
        current = status(None)
        current['current_task'] = {'task_id': 'synthetic-task', 'authoring': report, 'next_actions': options}
        status_view = production_status_view.summary(self.root, current)
        self.assertEqual(status_view['next_action']['alternatives'], options)
        self.assertNotIn('--choices', status_view['next_action']['argv'])

    def test_recording_summary_uses_verified_candidate_objects_and_original_destination(self):
        prepared = freeze({'run': 'synthetic-run', 'task': {'recording': {'character': 'fixture', 'slot': 'front'}}})
        rows = freeze([{'event': 'candidate', 'sha256': 'a' * 64,
            'data': {'output_index': 2, 'files': [{'path': 'journal/output.png', 'sha256': 'b' * 64}]}}])
        loaded = RunView(self.root / 'production/runs/synthetic-run', {}, prepared, {}, rows, None, None, {}, {})
        report = loaded.recording_summary()
        self.assertEqual(report['destination'], {'character': 'fixture', 'slot': 'front'})
        self.assertEqual(report['destination_scope'], 'saved-generation')
        self.assertEqual(report['outputs'][0]['candidate'], 'a' * 64)
        self.assertEqual(report['outputs'][0]['files'][0]['path'], str(loaded.directory / 'objects' / ('b' * 64)))
        report['destination']['slot'] = 'changed'
        self.assertEqual(prepared['task']['recording']['slot'], 'front')

    def test_status_summary_obeys_its_public_schema_and_preserves_authored_requirements(self):
        import production_operations as workflow
        report = status(requirements([grant('a'), grant('b')]))
        report['runs'][0]['authored'] = {'state': 'finished', 'input_verified': True,
            'saved': 'f' * 64, 'delivered': None, 'reviewed': None, 'requirements': ['delivery'],
            'missing': ['delivery'], 'completion_state': 'delivery-required',
            'unresolved': [], 'artifact': 'saved/delivery.txt'}
        result = views.present(self.root, report, command='status', run='synthetic-run')
        workflow.schema_check(result, 'status-summary')
        self.assertEqual(result['runs'][0]['authored'], report['runs'][0]['authored'])
        requirement = result['runs'][0]['authorization_requirements']['requirements'][0]
        requirement['eligible_grants'] = [{'grant': str(index), 'actor': 'Synthetic actor'} for index in range(9)]
        with self.assertRaises(ValueError):
            workflow.schema_check(result, 'status-summary')

    def test_reopened_draft_summary_links_the_source_run_without_repeating_its_task_and_reading_index(self):
        selected = {'run': 'saved-source-run', 'input_sha256': 'a' * 64,
            'task_path': 'production/runs/saved-source-run/inputs/production-task.json',
            'target_identity': {'execution': 'external', 'model': 'synthetic-model'},
            'assessment_required': ['Assess the copied source applications.'],
            'freshness': {'diagnostics': [], 'notices': []},
            'task': {'sources': [{'id': f'source-{index}', 'reason': 'Retained source meaning.' * 40}
                                 for index in range(30)]},
            'route_reading': {'documents': ['references/runtime/source-' + str(index) + '.md' for index in range(60)]},
            'required_action': 'Keep the source input distinct from the selected output candidate.',
            'next_action': {'command': 'inspect-inputs', 'argv': ['python', '--from-run', 'saved-source-run'],
                            'reason': 'Inspect the existing source owner.'}}
        report = {'state': 'draft', 'choices_file': 'work/reopened/choices.json', 'choices': {'authoring': {}},
            'derived_from': {'task': {'run': 'saved-source-run', 'input_sha256': 'a' * 64},
                             'source_run': selected, 'output_selection_required': True},
            'unresolved': [], 'next_actions': []}
        before = copy.deepcopy(report)
        result = views.present(self.root, report, command='draft-inputs')
        source = result['derived_from']['source_run']
        self.assertNotIn('task', source)
        self.assertNotIn('route_reading', source)
        for name in ('run', 'input_sha256', 'task_path', 'target_identity', 'assessment_required',
                     'freshness', 'required_action', 'next_action'):
            self.assertEqual(source[name], selected[name])
        self.assertTrue(result['derived_from']['output_selection_required'])
        self.assertEqual(source['read_action']['command'], 'inspect-inputs')
        self.assertEqual(source['read_action']['argv'][-4:], ['--from-run', 'saved-source-run', '--view', 'full'])
        import production_workflow
        parsed = production_workflow.build_parser().parse_args(source['read_action']['argv'][2:])
        self.assertEqual((parsed.command, parsed.from_run, parsed.view), ('inspect-inputs', 'saved-source-run', 'full'))
        self.assertLess(len(c.encoded(result)), len(c.encoded(report)) // 3)
        self.assertEqual(c.load(self.root / result['full_report']), before)
        self.assertEqual(report, before)

    def test_source_inspection_summary_uses_the_same_complete_source_owner(self):
        source = {'run': 'saved-source-run', 'input_sha256': 'a' * 64,
            'task_path': 'task.json', 'task': {'direction': 'Retained task body.' * 200},
            'route_reading': {'documents': ['required-reading'] * 40},
            'assessment_required': ['Assess this source.']}
        result = views.summarize(self.root, {'state': 'inspection', 'source_run': source,
            'task': {'run': 'saved-source-run', 'input_sha256': 'a' * 64}, 'unresolved': []},
            command='inspect-inputs')
        self.assertEqual(result['source_run']['run'], 'saved-source-run')
        self.assertEqual(result['source_run']['assessment_required'], ['Assess this source.'])
        self.assertNotIn('task', result['source_run'])
        self.assertNotIn('route_reading', result['source_run'])
        self.assertEqual(result['source_run']['read_action']['command'], 'inspect-inputs')

    def test_source_summary_keeps_output_reuse_owners_without_choosing_a_candidate(self):
        read = {'operation': 'status', 'argv': ['python', '--run', 'saved-source-run', '--view', 'full'],
                'external_effect': False}
        repair = 'Use authoring_guide.source_acquisition and the owning reference selector for the selected output.'
        reuse = {'meaning': 'Reopening retains saved input; an output is selected separately.',
            'automatic_output_selection': False, 'read_action': read, 'required_action': repair,
            'captured_outputs': [{'candidate': f'candidate-{index}', 'artifact': 'image',
                                  'files': [{'path': f'objects/image-{index}', 'sha256': 'b' * 64, 'size': 123}]}
                                 for index in range(20)]}
        source = {'run': 'saved-source-run', 'input_reuse': reuse}
        report = {'state': 'draft', 'choices': {'authoring': {}},
                  'derived_from': {'source_run': source}, 'unresolved': [], 'next_actions': []}
        result = views.present(self.root, report, command='draft-inputs')
        shown = result['derived_from']['source_run']['input_reuse']
        self.assertFalse(shown['automatic_output_selection'])
        self.assertEqual(shown['read_action'], read)
        self.assertEqual(shown['required_action'], repair)
        self.assertEqual(shown['captured_outputs'], reuse['captured_outputs'][:8])
        self.assertEqual(shown['captured_output_count'], 20)
        self.assertEqual(shown['captured_outputs_omitted'], 12)
        self.assertEqual(c.load(self.root / result['full_report']), report)

    def test_status_summary_counts_route_documents_and_shows_next_action_before_repeated_context(self):
        import production_operations as workflow
        report = status(None)
        report['current_task'] = {'task_id': 'synthetic-task', 'production_run': 'synthetic-run',
            'focus': 'execution', 'next_actions': [copy.deepcopy(report['runs'][0]['next_action'])],
            'authoring': {'state': 'authoring-state', 'task_id': 'synthetic-task', 'pending': False,
                'next_actions': [], 'inputs': [{'state': 'choices', 'current': True,
                    'directory': 'work/current', 'choices': 'work/current/choices.json',
                    'route_scope': {'route': 'generation', 'operation': 'prepare', 'execution': 'external',
                        'features': ['production-spec'], 'model': 'synthetic-model', 'service': 'synthetic-service',
                        'documents': ['references/runtime/long-source-document-' + str(index) + '.md'
                                      for index in range(80)]},
                    'unresolved': [{'field': 'authoring.task.direction', 'file': 'work/current/choices.json',
                        'required_action': 'Complete this actual authored choice.'}]}]}}
        before = copy.deepcopy(report)
        result = views.present(self.root, report, command='status', run='synthetic-run')
        workflow.schema_check(result, 'status-summary')
        scope = result['current_task']['authoring']['inputs'][0]['route_scope']
        self.assertEqual(scope['document_count'], 80)
        self.assertNotIn('documents', scope)
        for name in ('route', 'operation', 'execution', 'features', 'model', 'service'):
            self.assertEqual(scope[name], report['current_task']['authoring']['inputs'][0]['route_scope'][name])
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        self.assertLess(rendered.index('\n  "next_action"'), rendered.index('\n  "current_task"'))
        self.assertLess(rendered.index('\n  "full_report"'), rendered.index('\n  "current_task"'))
        self.assertIn('\n  "next_action"', rendered[:2000])
        self.assertEqual(result['next_action'], report['runs'][0]['next_action'])
        self.assertEqual(result['runs'][0]['next_action'], report['runs'][0]['next_action'])
        authoring = result['current_task']['authoring']
        [identifier] = authoring['inputs'][0]['diagnostic_ids']
        self.assertEqual(next(row for row in authoring['diagnostics'] if row['id'] == identifier)['required_action'],
                         'Complete this actual authored choice.')
        self.assertEqual(c.load(self.root / result['full_report']), before)
        self.assertEqual(report, before)

    def test_long_studio_summary_bounds_history_and_keeps_exact_full_report(self):
        import production_operations as workflow
        report = long_authoring_status()
        # The same current read can replace several older source digests.
        for change in report['current_task']['authoring']['inputs'][1]['unresolved'][0]['source_changes']['changes']:
            change['before'] = 'c' * 64
        before = copy.deepcopy(report)
        result = views.present(self.root, report, command='status', run='synthetic-run')
        workflow.schema_check(result, 'status-summary')
        authoring = result['current_task']['authoring']
        for name in ('inputs', 'input_options', 'readings', 'decision_drafts'):
            displayed, counts = authoring[name], authoring[name + '_summary']
            self.assertLessEqual(len(displayed), views.DETAIL_LIMIT)
            self.assertEqual(counts['total'], len(report['current_task']['authoring'][name]))
            self.assertEqual(counts['omitted'], counts['total'] - len(displayed))
            self.assertEqual(counts['full_report'], result['full_report'] + '#/current_task/authoring/' + name)
        self.assertEqual(authoring['inputs'][0]['choices'], 'work/branch-063/choices.json')
        self.assertEqual(authoring['decision_drafts_summary']['unrelated'], 60)
        self.assertTrue(all(row['run'] == 'synthetic-run' and row['relation'] == 'selected-run'
                            for row in authoring['decision_drafts']))
        self.assertEqual(len(authoring['diagnostics']), 1)
        [issue] = authoring['diagnostics']
        self.assertEqual(authoring['context']['input']['diagnostic_ids'], [issue['id']])
        self.assertNotIn('unresolved', authoring['context']['input'])
        self.assertEqual(issue['changed_sources_summary']['total'], 80)
        self.assertEqual(issue['changed_sources_summary']['omitted'], 72)
        self.assertEqual(len(result['blockers']), 1)
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        self.assertNotIn('a' * 64, json.dumps(authoring))
        self.assertNotIn('b' * 64, json.dumps(authoring))
        self.assertNotIn('unrelated-run', rendered)
        self.assertEqual(rendered.count('/skill/scripts/execution_routes.py'), 1)
        self.assertEqual(rendered.count('references/runtime/changed-source-000.md'), 1)
        self.assertLess(rendered.index('\n  "blockers"'), rendered.index('\n  "current_task"'))
        self.assertLess(rendered.index('\n  "run"'), rendered.index('\n  "current_task"'))
        self.assertLessEqual(len(rendered.encode('utf-8')), 32 * 1024)
        self.assertEqual(c.load(self.root / result['full_report']), before)
        self.assertEqual(report, before)

    def test_prepared_input_summary_keeps_current_work_without_repeating_authoring_navigation(self):
        import production_operations as workflow
        report = prepared_authoring_status(self.root)
        before = copy.deepcopy(report)
        result = views.present(self.root, report, command='status', run='synthetic-run')
        workflow.schema_check(result, 'status-summary')
        authored = result['current_task']['authoring']
        self.assertFalse(authored['pending'])
        self.assertNotIn('stage_actions', authored)
        self.assertNotIn('fresh_context_action', json.dumps(authored))
        self.assertEqual(authored['stage_actions_summary']['total'], 3)
        self.assertEqual(authored['stage_actions_summary']['full_report'],
                         result['full_report'] + '#/current_task/authoring/stage_actions')
        selected = authored['context']['input']
        self.assertEqual(selected['input_ref'], '#/current_task/authoring/inputs/0')
        self.assertNotIn('editable_locations', selected)
        self.assertNotIn('authoring_stage', selected)
        self.assertEqual(authored['inputs'][0]['editable_locations'],
                         report['current_task']['authoring']['inputs'][0]['editable_locations'])
        self.assertEqual(result['next_action'], report['runs'][0]['next_action'])
        self.assertEqual({row['question_id'] for row in result['blockers'] if 'question_id' in row},
                         {'open-a', 'open-b'})
        self.assertTrue(any(row.get('kind') == 'work-blocker' for row in result['blockers']))
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8')), 32 * 1024)
        self.assertEqual(c.load(self.root / result['full_report']), before)
        self.assertEqual(report, before)

    def test_changed_prepared_input_keeps_its_current_read_and_stage_actions(self):
        report = prepared_authoring_status(self.root)
        authored = report['current_task']['authoring']
        authored['pending'] = True
        authored['inputs'][0]['changed_since_save'] = True
        authored['context']['input']['changed_since_build'] = True
        problem = {'code': 'AUTHOR_INPUT_REQUIRED', 'field': 'authoring.delivery',
            'message': 'Assess the actual edited source.', 'required_action': 'Read and assess the current prompt.'}
        authored['authoring_stage']['unresolved'] = [problem]
        result = views.present(self.root, report, command='status', run='synthetic-run')
        displayed = result['current_task']['authoring']
        self.assertEqual(displayed['fresh_context_action']['argv'], authored['fresh_context_action']['argv'])
        self.assertEqual([row['argv'] for row in displayed['stage_actions']],
                         [row['argv'] for row in authored['stage_actions']])
        self.assertIn('authoring.delivery', {row.get('field') for row in result['blockers']})
        self.assertEqual(displayed['inputs'][0]['changed_since_save'], True)
        self.assertEqual(c.load(self.root / result['full_report']), report)

    def test_implementation_notice_keeps_changed_locations_and_complete_hash_evidence(self):
        report = prepared_authoring_status(self.root)
        changes = [{'path': f'scripts/changed-{number}.py', 'expected': 'a' * 64, 'actual': 'b' * 64}
                   for number in range(11)]
        changes[0]['actual'] = None
        changes[1]['expected'] = None
        notice = {'code': 'IMPLEMENTATION_CHANGED', 'severity': 'warning', 'phase': 'implementation',
            'message': '11 implementation files changed after preparation.',
            'required_action': 'No action is needed to continue this saved run. Read current material before preparing again.',
            'expected': 'a' * 64, 'actual': 'b' * 64, 'changed_files': changes}
        report['runs'][0]['freshness_notices'] = [notice]
        result = views.present(self.root, report, command='status', run='synthetic-run')
        projected = result['runs'][0]['freshness_notices'][0]
        for name in ('code', 'severity', 'phase', 'message', 'required_action'):
            self.assertEqual(projected[name], notice[name])
        self.assertNotIn('expected', projected)
        self.assertNotIn('actual', projected)
        self.assertEqual(projected['changed_files'],
                         [item['path'] for item in changes[:8]])
        self.assertEqual(projected['unavailable_files'], [changes[0]['path']])
        self.assertEqual(projected['added_files'], [changes[1]['path']])
        self.assertEqual(projected['changed_files_summary'],
                         {'total': 11, 'omitted': 3, 'full_report': result['full_report']})
        self.assertEqual(c.load(self.root / result['full_report'])['runs'][0]['freshness_notices'], [notice])
        self.assertEqual(result['next_action'], report['runs'][0]['next_action'])
        self.assertEqual({row['question_id'] for row in result['blockers'] if 'question_id' in row},
                         {'open-a', 'open-b'})
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8')), 32 * 1024)

    def test_omitted_input_branches_keep_every_distinct_unresolved_finding(self):
        report = long_authoring_status()
        authored = report['current_task']['authoring']
        for number, row in enumerate(authored['inputs']):
            row['unresolved'] = [{'code': 'AUTHOR_INPUT_REQUIRED', 'field': 'criterion-' + str(number),
                'file': row['choices'], 'message': 'The criterion needs its actual authored answer.',
                'required_action': 'Complete this criterion at its owning editable input.'}]
        authored['input_options'] = []
        authored['context']['input'] = None
        result = views.present(self.root, report, command='status', run='synthetic-run')
        projected = result['current_task']['authoring']
        self.assertEqual(len(projected['inputs']), 8)
        self.assertEqual(len(projected['diagnostics']), 64)
        self.assertEqual(len(result['blockers']), 64)
        self.assertEqual({row['field'] for row in result['blockers']}, {'criterion-' + str(number) for number in range(64)})
        self.assertEqual(c.load(self.root / result['full_report']), report)

    def test_input_inspection_keeps_every_referenced_diagnostic_in_its_summary(self):
        report = long_authoring_status()['current_task']['authoring']
        report['diagnostics'] = [{'code': 'AUTHOR_INPUT_REQUIRED',
            'field': 'selected-branch', 'message': 'Choose the branch to continue.',
            'required_action': 'Inspect the current editable branch.'}]
        before = copy.deepcopy(report)
        result = views.present(self.root, report, command='inspect-inputs',
                               choices='work/branch-063/choices.json')
        index = {row['id']: row for row in result['diagnostics']}
        self.assertEqual(len(index), 2)
        for row in [*result['inputs'], *result['input_options'], result['context']['input']]:
            self.assertTrue(set(row['diagnostic_ids']).issubset(index))
        self.assertEqual({row['code'] for row in index.values()},
                         {'AUTHOR_INPUT_REQUIRED', 'TARGET_GUIDANCE_REQUIRED'})
        self.assertEqual(c.load(self.root / result['full_report']), before)
        self.assertEqual(report, before)

        report['diagnostics'] = []
        result = views.present(self.root, report, command='inspect-inputs',
                               choices='work/branch-063/choices.json')
        [issue] = result['diagnostics']
        self.assertEqual(issue['code'], 'TARGET_GUIDANCE_REQUIRED')
        self.assertEqual(result['context']['input']['diagnostic_ids'], [issue['id']])
        self.assertEqual(c.load(self.root / result['full_report']), report)

    def test_large_action_alternatives_keep_counts_and_their_complete_report_owner(self):
        report = status(None)
        next_action = report['runs'][0]['next_action']
        next_action['alternatives'] = [{**copy.deepcopy(next_action), 'draft': f'work/choice-{number}.json'}
                                       for number in range(54)]
        result = views.present(self.root, report, command='status', run='synthetic-run')
        for displayed in (result['next_action'], result['runs'][0]['next_action']):
            self.assertEqual(len(displayed['alternatives']), 8)
            self.assertEqual(displayed['alternatives_summary'], {'total': 54, 'omitted': 46,
                'full_report': result['full_report'] + '#/runs/0/next_action/alternatives'})
        self.assertEqual(c.load(self.root / result['full_report']), report)

    def test_answered_question_history_does_not_hide_any_open_question_or_blocker(self):
        report = long_authoring_status()
        work = report['current_task']['authoring']['context']['work']
        work['questions'] = [{'question_id': str(number), 'question': f'Answered historical question {number}.',
                             'answer': 'Long saved answer. ' * 100, 'state': 'answered'} for number in range(60)] + [
            {'question_id': f'open-{number}', 'question': f'Current open question {number}.', 'state': 'open'}
            for number in range(12)]
        work['blocked_on'] = 'An independent current prerequisite.'
        result = views.present(self.root, report, command='status', run='synthetic-run')
        current = result['current_task']['authoring']['context']['work']
        self.assertEqual(len(current['questions']), 12)
        self.assertEqual(current['questions_summary']['total'], 72)
        self.assertEqual(current['questions_summary']['omitted'], 60)
        self.assertEqual({row['question_id'] for row in result['blockers'] if 'question_id' in row},
                         {f'open-{number}' for number in range(12)})
        self.assertTrue(any(row.get('kind') == 'work-blocker' for row in result['blockers']))
        self.assertNotIn('Answered historical question', json.dumps(result))
        self.assertEqual(c.load(self.root / result['full_report']), report)

    def test_curation_summary_retains_unconfirmed_assessments_and_their_saved_owner(self):
        report = {'draft_file': 'work/adoption.json', 'schema': 'adoption.schema.json',
            'required_action': 'Complete actual adoption decisions.',
            'choices': {'run': 'synthetic-run', 'candidate': 'candidate', 'review': 'review',
                'selection': 'selection', 'scope': 'sheet', 'influence': 'identity', 'grant': None, 'reason': '',
                'shared_stop_assessments': {'authorization': 'selection-authority', 'authority_event': 'event',
                    'confirmed': None, 'basis': {'instruction_evidence': 'Retained actual evidence. ' * 200},
                    'assessments': [{'id': 'stop', 'condition': 'Actual stop definition.', 'clear': True,
                                     'evidence': 'Actual retained evidence.'}]}, 'additional_stop_assessments': []},
            'reading_action': {'command': 'read', 'argv': ['python', '/skill/scripts/execution_routes.py', 'read',
                'adoption', '--operation', 'adopt', '--scope', 'sheet'], 'reason': 'Read this operation.'},
            'next_action': {'command': 'adopt', 'argv': ['python', 'production_workflow.py', 'adopt'],
                            'requires_author_input': True, 'reason': 'Complete the actual decisions first.'}}
        original = copy.deepcopy(report)
        result = views.present(self.root, report, command='draft-adoption')
        self.assertIsNone(result['shared_stop_assessments']['confirmed'])
        self.assertEqual(result['shared_stop_assessments']['assessment_count'], 1)
        self.assertEqual(result['shared_stop_assessments']['full_report'],
                         result['full_report'] + '#/choices/shared_stop_assessments')
        self.assertIn('/shared_stop_assessments/confirmed', [row['pointer'] for row in result['unresolved']])
        self.assertTrue(all(row['file'] == 'work/adoption.json' for row in result['unresolved']))
        self.assertEqual(result['binding']['selection'], 'selection')
        self.assertEqual(result['reading_action'], report['reading_action'])
        self.assertEqual(result['next_action'], report['next_action'])
        self.assertEqual(c.load(self.root / result['full_report']), original)
        self.assertEqual(report, original)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
