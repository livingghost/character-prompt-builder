"""One authored adoption decision retains the selected work and recoverable proof."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import adoption_workflow
import execution_contract as c
import production_adoption as authored
import production_authority_drafts as authority_drafts
import production_acceptance as acceptance
import production_case_fixtures as f
import production_execution as execution
import production_fixtures as fixture
import production_store as store
import production_operations as workflow
import studio_workspace as studio
import studio_reference
import test_production_adoption as baseline
import transport_synthetic
from production_diagnostics import ProductionError


class AuthoredAdoptionTests(unittest.TestCase):
    setUpClass = classmethod(baseline.AdoptionTests.setUpClass.__func__)
    select = baseline.AdoptionTests.select
    import_authority = baseline.AdoptionTests.import_authority
    withdraw_adoption = baseline.AdoptionTests.withdraw_adoption

    def setUp(self):
        baseline.AdoptionTests.setUp(self)
        self.select()
        authority = store.authority(self.root, self.task['task_id'])
        authority['stop_conditions'] = [{'id': 'canonical-use',
            'text': 'Stop if canonical reuse exceeds the explicitly synthetic fixture instruction.'}]
        self.import_authority(authority)

    def draft(self, **kwargs):
        return authored.draft(self.root, self.run, self.candidate,
            scope=kwargs.pop('scope', 'sheet'), influence=kwargs.pop('influence', 'identity'), **kwargs)

    def decide(self, value, *, stop_clear=True):
        value = copy.deepcopy(value)
        value.update(at='2000-01-02T00:00:00Z',
                     reason='Explicit synthetic canonical-use decision; this is not user consent.')
        if value['continuity_decision'] is not None:
            value['continuity_decision'].update(character_id='robot', continuity='recurring',
                basis={'path': 'adoption-basis.txt', 'locator': 'whole synthetic author decision'})
        self.assertEqual([item['id'] for item in value['additional_stop_assessments']], ['canonical-use'])
        if stop_clear:
            value['additional_stop_assessments'][0].update(clear=True,
                evidence='The fixture instruction permits this named image as a synthetic canonical reference only.')
        return value

    def save(self, value, path='decisions/adoption.json'):
        f.write(self.root / path, value)
        return path

    def changed_condition(self):
        authority = store.authority(self.root, self.task['task_id'])
        authority['stop_conditions'][0]['text'] = 'Stop unless this retained fixture image remains within the revised instruction.'
        self.import_authority(authority)

    def assess_retained(self, value):
        value = copy.deepcopy(value)
        self.assertEqual(value['additional_stop_assessments'], [{'id': 'canonical-use',
            'condition': 'Stop unless this retained fixture image remains within the revised instruction.',
            'clear': False, 'evidence': ''}])
        value['reason'] = 'Continue this exact synthetic claim under the explicitly revised fixture instruction.'
        value['additional_stop_assessments'][0].update(clear=True,
            evidence='The revised fixture instruction still authorizes this same retained image and canonical destination.')
        return value

    def apply(self, value=None, *, path='decisions/adoption.json'):
        if value is not None:
            self.save(value, path)
        return authored.apply(self.root, self.run, decision_file=path, settings=self.settings)

    def adoption_rows(self):
        return [row for row in store.event_rows(self.root, self.run)
                if row['event'] in {'adoption-claim', 'adoption-result'}]

    def journal_path(self):
        return adoption_workflow._journal_path(studio.character_home(self.root, 'robot'), self.row['iteration_id'])

    def cli(self, *args, stdin=None, code=0):
        command = [sys.executable, str(Path(__file__).with_name('production_workflow.py')),
                   *args, '--root', str(self.root), '--run', self.run]
        result = subprocess.run(command, input=stdin, text=True, encoding='utf-8', capture_output=True,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, timeout=120)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_draft_derives_subject_and_only_actual_unanswered_stop_conditions(self):
        before = store.event_rows(self.root, self.run)
        value = self.draft()
        workflow.schema_check(value, 'adoption')
        self.assertEqual((value['character'], value['iteration'], value['slot'], value['image_sha256']),
                         ('robot', self.row['iteration_id'], self.row['slot'], self.row['result']['sha256']))
        self.assertEqual(value['selection'], workflow.find(before, 'selection')['sha256'])
        self.assertEqual(value['review'], workflow.latest_review(before, self.candidate)['sha256'])
        self.assertEqual(value['grant'], 'fixture-grant')
        self.assertIsNone(value['at'])
        self.assertEqual(value['reason'], '')
        self.assertEqual(value['additional_stop_assessments'], [{'id': 'canonical-use',
            'condition': 'Stop if canonical reuse exceeds the explicitly synthetic fixture instruction.',
            'clear': False, 'evidence': ''}])
        self.assertIsNone(value['continuity_decision']['continuity'])
        self.assertEqual(store.event_rows(self.root, self.run), before)
        self.assertFalse(self.journal_path().exists())

    def test_one_decision_derives_authority_and_reuses_existing_image(self):
        value = self.decide(self.draft())
        before = store.event_rows(self.root, self.run)
        original = studio.read_iteration_records(studio.character_home(self.root, 'robot'))
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('No generation for adoption')), \
             patch.object(studio, 'iterate', side_effect=AssertionError('No new iteration for adoption')):
            result = self.apply(value)
            repeated = self.apply()
        self.assertEqual(result['adoption_claim'], repeated['adoption_claim'])
        rows = store.event_rows(self.root, self.run)
        self.assertEqual([row['event'] for row in rows[len(before):]],
                         ['authorization', 'adoption-claim', 'operation-start', 'adoption-result'])
        self.assertEqual([row['iteration_id'] for row in original],
                         [row['iteration_id'] for row in studio.read_iteration_records(studio.character_home(self.root, 'robot'))])
        authorization = rows[len(before)]
        self.assertEqual(authorization['data']['request']['actor'], fixture.ACTOR)
        self.assertEqual(authorization['data']['request']['stop_assessments'],
                         [{key: value['additional_stop_assessments'][0][key] for key in ('id', 'clear', 'evidence')}])
        claim = workflow.find(rows, 'adoption-claim', result['adoption_claim'])
        approval = c.decode(workflow.read_run(self.root, self.run).evidence.read(claim['data']['files'][0]['sha256']))
        self.assertEqual(approval['by'], fixture.ACTOR)
        self.assertEqual(approval['authority_sha256'], value['authority_sha256'])
        self.assertEqual(claim['data']['intent']['payload']['approval_sha256'], c.content_id(approval))
        self.assertEqual(approval['continuity_decision']['basis']['locator'], 'whole synthetic author decision')
        self.assertIn(approval['continuity_decision']['basis']['path'],
                      [item['path'] for item in authorization['data']['files']])
        (self.root / 'adoption-basis.txt').unlink()
        studio_reference.validate_source(studio_reference.current_source(self.root, 'robot', 'base.front'))

    def test_unanswered_assessment_cannot_commit_a_claim(self):
        value = self.decide(self.draft(), stop_clear=False)
        before = store.event_rows(self.root, self.run)
        with self.assertRaises(ValueError):
            self.apply(value)
        self.assertEqual(store.event_rows(self.root, self.run), before)
        self.assertFalse(self.journal_path().exists())

    def test_new_destination_receipt_invalidates_an_uncommitted_decision(self):
        value = self.decide(self.draft())
        studio.accept(self.root, 'robot', self.row['iteration_id'])
        before = store.event_rows(self.root, self.run)
        with self.assertRaises(ProductionError) as caught:
            self.apply(value)
        self.assertEqual(caught.exception.diagnostic.code, 'ADOPTION_DECISION_CHANGED')
        self.assertEqual(store.event_rows(self.root, self.run), before)
        self.assertFalse(self.journal_path().exists())

    def test_changed_stop_wording_invalidates_uncommitted_assessments(self):
        value = self.decide(self.draft())
        authority = store.authority(self.root, self.task['task_id'])
        authority['stop_conditions'][0]['text'] = 'Stop until this additional canonical-use condition is assessed.'
        self.import_authority(authority)
        before = store.event_rows(self.root, self.run)
        with self.assertRaises(ProductionError) as caught:
            self.apply(value)
        self.assertEqual(caught.exception.diagnostic.code, 'ADOPTION_DECISION_CHANGED')
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_unrelated_grant_changes_do_not_discard_a_relevant_decision(self):
        value = self.decide(self.draft())
        authority = store.authority(self.root, self.task['task_id'])
        other = copy.deepcopy(authority['grants'][0])
        other.update(id='separate-direction-grant', operations=['direction'], targets=['purpose'],
                     request_scope=None, submission_validation_modes=[])
        authority['grants'].append(other)
        self.import_authority(authority)
        result = self.apply(value)
        self.assertEqual(result['data']['result']['status'], 'sheet-bound')

    def test_completed_claim_recovery_never_reinstates_withdrawn_canonical_use(self):
        result = self.apply(self.decide(self.draft()))
        self.withdraw_adoption()
        sheet = studio.character_home(self.root, 'robot') / 'sheet/sheet-data.json'
        before = sheet.read_bytes()
        with patch.object(adoption_workflow, 'adopt', side_effect=AssertionError('Only historical repair is permitted')):
            recovered = authored.apply(self.root, self.run, claim_id=result['adoption_claim'])
        self.assertEqual(recovered['adoption_claim'], result['adoption_claim'])
        self.assertEqual(sheet.read_bytes(), before)
        self.assertIsNone(c.load(sheet)['slots']['base.front']['current'])
        fresh = self.decide(self.draft())
        fresh['at'] = '2000-01-03T00:00:00Z'
        restored = self.apply(fresh, path='decisions/new-use.json')
        self.assertNotEqual(restored['adoption_claim'], result['adoption_claim'])
        self.assertIsNotNone(c.load(sheet)['slots']['base.front']['current'])

    def test_interrupted_apply_discovers_and_recovers_claim_without_authoring_files(self):
        value = self.decide(self.draft())
        self.save(value)
        append = workflow.append_record

        def stop_before_result(loaded, event, data):
            if event == 'adoption-result':
                raise OSError('Synthetic interruption after Studio applied the decision')
            return append(loaded, event, data)

        with patch.object(workflow, 'append_record', side_effect=stop_before_result), self.assertRaises(OSError):
            self.apply()
        claim = workflow.find(store.event_rows(self.root, self.run), 'adoption-claim')
        (self.root / 'decisions/adoption.json').unlink()
        (self.root / 'adoption-basis.txt').unlink()
        status = execution.status(self.root, self.run)
        workflow.schema_check(status, 'status')
        actions = status['runs'][0]['adoption_actions']
        action = next(item for item in actions if item.get('claim') == claim['sha256'])
        self.assertFalse(action['requires_author_input'])
        self.assertEqual(action['argv'][-2:], ['--claim', claim['sha256']])
        result = authored.apply(self.root, self.run, claim_id=claim['sha256'])
        self.assertEqual(result['adoption_claim'], claim['sha256'])
        self.assertEqual([row['event'] for row in self.adoption_rows()], ['adoption-claim', 'adoption-result'])
        studio_reference.validate_source(studio_reference.current_source(self.root, 'robot', 'base.front'))

    def test_current_revocation_is_checked_when_recovering_a_claim(self):
        value = self.decide(self.draft())
        with patch.object(adoption_workflow, 'adopt', side_effect=OSError('Synthetic pause before the local effect')):
            with self.assertRaises(OSError):
                self.apply(value)
        claim = workflow.find(store.event_rows(self.root, self.run), 'adoption-claim')
        self.changed_condition()
        authority = store.authority(self.root, self.task['task_id'])
        authority['grants'][0]['revoked_at'] = '2000-01-01T00:00:00Z'
        self.import_authority(authority)
        with self.assertRaises(ProductionError) as caught:
            authored.apply(self.root, self.run, claim_id=claim['sha256'])
        self.assertEqual(caught.exception.diagnostic.code, 'GRANT_REVOKED')
        self.assertFalse(self.journal_path().exists())

    def test_low_level_approval_without_assessment_basis_still_refuses_changed_conditions(self):
        self.assertNotIn('authority_sha256', self.approval)
        intent = workflow.adoption_intent(self.root, self.run, self.candidate,
            'robot', self.row['iteration_id'], self.approval)
        request = workflow.draft_authorization(self.root, self.run, 'fixture-grant', intent)
        request['reason'] = 'Explicit synthetic low-level adoption authorization; not user consent.'
        for assessment in request['stop_assessments']:
            assessment.update(clear=True, evidence='The synthetic fixture instruction permits the selected canonical use.')
        authorization = workflow.authorize_value(self.root, self.run, request, evidence_files=[])['sha256']
        with patch.object(adoption_workflow, 'adopt', side_effect=OSError('Synthetic pause before the local effect')):
            with self.assertRaises(OSError):
                baseline.AdoptionTests.adopt(self, authorization)
        rows = store.event_rows(self.root, self.run)
        self.changed_condition()
        with patch.object(adoption_workflow, 'adopt') as effect, self.assertRaises(ProductionError) as caught:
            baseline.AdoptionTests.adopt(self, authorization)
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_MISMATCH')
        self.assertEqual(caught.exception.diagnostic.pointer, '$.stop_assessments')
        effect.assert_not_called()
        self.assertEqual(store.event_rows(self.root, self.run), rows)

    def test_partial_sheet_effect_keeps_its_claim_and_approval_when_reassessed(self):
        value = self.decide(self.draft())
        with patch.object(adoption_workflow, '_bind_sheet', side_effect=OSError('Synthetic pause before binding')):
            with self.assertRaises(OSError):
                self.apply(value)
        rows = store.event_rows(self.root, self.run)
        claim = workflow.find(rows, 'adoption-claim')
        start = workflow.find(rows, 'operation-start')
        prior = c.load(self.journal_path())
        self.assertEqual(prior['status'], 'candidate-accepted')
        self.changed_condition()
        with self.assertRaises(ProductionError) as caught:
            authored.apply(self.root, self.run, claim_id=claim['sha256'])
        self.assertEqual(caught.exception.diagnostic.code, 'ADOPTION_DECISION_CHANGED')
        self.assertIn('--claim ' + claim['sha256'], caught.exception.diagnostic.required_action)
        self.assertEqual(store.event_rows(self.root, self.run), rows)
        self.assertEqual(c.load(self.journal_path()), prior)
        path = 'decisions/reassessed-canonical-use.json'
        self.cli('draft-adoption', '--claim', claim['sha256'], '--out', path)
        reassessment = self.assess_retained(c.load(self.root / path))
        self.assertEqual(reassessment['approval'], prior['approval'])
        self.save(reassessment, path)
        result = self.cli('adopt', '--file', path)
        self.assertEqual(result['adoption_claim'], claim['sha256'])
        self.assertEqual(c.load(self.journal_path())['approval'], prior['approval'])
        rows = store.event_rows(self.root, self.run)
        self.assertEqual([row for row in rows if row['event'] == 'operation-start'
                          and row['data'].get('claim') == claim['sha256']], [start])
        self.assertEqual(len([row for row in rows if row['event'] == 'adoption-claim']), 1)
        self.assertEqual(len([row for row in rows if row['event'] == 'adoption-authority']), 1)
        self.assertEqual(result['data']['result']['status'], 'sheet-bound')

    def test_authorized_replacement_operator_keeps_the_original_approval_and_starts_once(self):
        with patch.object(adoption_workflow, 'adopt', side_effect=OSError('Synthetic pause before local ownership')):
            with self.assertRaises(OSError):
                self.apply(self.decide(self.draft()))
        claim = workflow.find(store.event_rows(self.root, self.run), 'adoption-claim')
        self.changed_condition()
        authority = store.authority(self.root, self.task['task_id'])
        authority['grants'][0]['actor'] = 'SYNTHETIC REPLACEMENT OPERATOR - NOT USER CONSENT'
        self.import_authority(authority)
        value = self.assess_retained(authored.draft_reassessment(self.root, self.run, claim['sha256']))
        result = self.apply(value, path='decisions/current-authority.json')
        rows = store.event_rows(self.root, self.run)
        link = workflow.find(rows, 'adoption-authority')
        starts = [row for row in rows if row['event'] == 'operation-start' and row['data'].get('claim') == claim['sha256']]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0]['data']['authorization_sha256'], link['data']['authorization'])
        self.assertEqual(result['adoption_claim'], claim['sha256'])
        self.assertEqual(c.load(self.journal_path())['approval']['by'], fixture.ACTOR)
        authorization = workflow.find(rows, 'authorization', link['data']['authorization'])
        self.assertEqual(authorization['data']['request']['actor'], authority['grants'][0]['actor'])

    def test_claim_lookup_matches_decision_content_across_line_endings(self):
        result = self.apply(self.decide(self.draft()))
        raw = (self.root / 'decisions/adoption.json').read_bytes().replace(b'\n', b'\r\n')
        claim = authored._claim_for_decision(workflow.read_run(self.root, self.run), raw)
        self.assertEqual(claim['sha256'], result['adoption_claim'])

    def test_saved_custom_draft_and_stdin_apply_share_one_public_contract(self):
        path = 'decisions/chosen-canonical-use.json'
        self.cli('draft-adoption', '--candidate', self.candidate, '--scope', 'sheet',
                 '--influence', 'identity', '--out', path)
        value = self.decide(c.load(self.root / path))
        self.save(value, path)
        status = self.cli('status', '--view', 'full')
        workflow.schema_check(status, 'status')
        actions = status['runs'][0]['adoption_actions']
        self.assertEqual(actions[0]['draft'], path)
        self.assertEqual(actions[0]['argv'][-2:], ['--file', path])
        self.assertTrue(actions[0]['requires_author_input'])
        result = self.cli('adopt', '--file', '-', stdin=c.encoded(value).decode())
        claim = result['adoption_claim']
        status = self.cli('status', '--view', 'full')
        workflow.schema_check(status, 'status')
        actions = status['runs'][0]['adoption_actions']
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['argv'][-2:], ['--claim', claim])
        self.assertFalse(actions[0]['requires_author_input'])
        self.assertEqual(self.cli('adopt', '--claim', claim)['adoption_claim'], claim)

    def test_catalog_recovery_uses_retained_record_and_existing_pack(self):
        authority = store.authority(self.root, self.task['task_id'])
        authority['grants'][0]['targets'].append('canon:catalog')
        self.import_authority(authority)
        registration = {'id': 'authored-adoption-fixture', 'label': 'Authored fixture', 'curation_status': 'curated',
            'category': 'species', 'prompt': 'a fictional test character', 'domains': ['shared'],
            'tags': ['fixture', 'character'],
            'search_terms': [{'phrase': 'authored adoption fixture', 'facet': 'species', 'weight': 1.0, 'source': 'author'}],
            'scaffold': {'family': 'direct-geometry-required', 'confidence': 'fallback'}}
        self.save(registration, 'decisions/registration.json')
        pack = Path(self.temp.name) / 'chosen-reference-pack'
        value = self.decide(self.draft(scope='catalog', registration_file='decisions/registration.json', pack_dir=pack))
        self.assertEqual(value['registration']['record_sha256'], adoption_workflow.digest(registration))
        with patch.object(adoption_workflow, 'enable_pack', side_effect=OSError('Synthetic activation interruption')):
            with self.assertRaises(OSError):
                self.apply(value)
        claim = workflow.find(store.event_rows(self.root, self.run), 'adoption-claim')
        pack_manifest = (pack / 'pack.json').read_bytes()
        pack_receipt = (pack / 'resources/adoption-receipt.json').read_bytes()
        original_approval = c.load(self.journal_path())['approval']
        start = workflow.find(store.event_rows(self.root, self.run), 'operation-start')
        (self.root / 'decisions/registration.json').unlink()
        (self.root / 'decisions/adoption.json').unlink()
        (self.root / 'adoption-basis.txt').unlink()
        self.changed_condition()
        reassessment = self.assess_retained(authored.draft_reassessment(self.root, self.run, claim['sha256']))
        result = self.apply(reassessment, path='decisions/catalog-reassessment.json')
        self.assertEqual(result['data']['result']['status'], 'catalog-registered')
        self.assertEqual((pack / 'pack.json').read_bytes(), pack_manifest)
        self.assertEqual((pack / 'resources/adoption-receipt.json').read_bytes(), pack_receipt)
        self.assertEqual(c.load(self.journal_path())['approval'], original_approval)
        self.assertEqual([row for row in store.event_rows(self.root, self.run) if row['event'] == 'operation-start'
                          and row['data'].get('claim') == claim['sha256']], [start])
        self.assertEqual([row['event'] for row in self.adoption_rows()], ['adoption-claim', 'adoption-result'])


class SelectionAdoptionAuthorityTests(unittest.TestCase):
    """One actual instruction, separate select/adopt authority and shared judgments."""
    setUpClass = classmethod(baseline.AdoptionTests.setUpClass.__func__)
    import_authority = baseline.AdoptionTests.import_authority

    def setUp(self):
        baseline.AdoptionTests.setUp(self)
        self.instruction = ('Explicit synthetic instruction: select this reviewed fixture in its existing Studio slot '
            'and use it as that slot\'s sheet identity reference. This fixture is not real user consent.')
        f.write(self.root / 'actual-curation.txt', self.instruction)
        authority = store.authority(self.root, self.task['task_id'])
        for grant in authority['grants']:
            grant['operations'] = [item for item in grant['operations'] if item not in {'select', 'adopt'}]
        authority['stop_conditions'] = [{'id': 'actual-scope',
            'text': 'Stop if the actual synthetic instruction does not cover this reviewed image and intended use.'}]
        self.import_authority(authority)

    def invoke(self, argv, *, expected=0):
        result = subprocess.run(argv, cwd=self.root, text=True, encoding='utf-8', capture_output=True,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, timeout=120)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def cli(self, command, *arguments, expected=0):
        return self.invoke([sys.executable, str(Path(__file__).with_name('production_workflow.py')),
            command, '--root', str(self.root), *arguments], expected=expected)

    def current_authority(self):
        return store.read_authority(self.root, self.task['task_id'])

    def author_update(self, report):
        value = copy.deepcopy(report['choices'])
        self.assertEqual(value['evidence'], {'path': None, 'locator': None, 'sha256': None})
        self.assertTrue(all(item['actor'] is None and item['mode'] is None and item['reason'] == ''
                            for item in value['grants']))
        value['evidence'].update(path='actual-curation.txt', locator='whole')
        for item in value['grants']:
            item.update(actor=fixture.ACTOR, mode='direct', reason='The explicit synthetic instruction permits ' + item['operation'] + '.')
        return value

    def import_update(self, value, path):
        f.write(self.root / path, value)
        return store.import_authority(self.root, path, expected=value['expected_event'], report_changes=True)

    def selected_slot(self, *, owner_allowance=None, halt_before_completion=False):
        update = self.author_update(authority_drafts.draft_authority_update(self.root, self.run,
            phase='selection', candidate=self.candidate))
        self.import_update(update, 'decisions/selection-authority.json')
        value = acceptance.draft(self.root, self.run, self.candidate, scope='studio-slot')
        value.update(reason='Explicit synthetic slot selection.', owner_acceptance=owner_allowance)
        for item in value['stop_assessments']:
            item.update(clear=True, evidence='The retained synthetic instruction covers this exact reviewed fixture and both requested uses.')
        f.write(self.root / 'decisions/acceptance.json', value)
        if halt_before_completion:
            with patch.object(workflow, 'complete', side_effect=OSError('Synthetic pause after slot acceptance')):
                with self.assertRaises(OSError):
                    acceptance.accept(self.root, self.run, decision_file='decisions/acceptance.json')
            result = {'selection': workflow.find(store.event_rows(self.root, self.run), 'selection')['sha256']}
        else:
            result = acceptance.accept(self.root, self.run, decision_file='decisions/acceptance.json')
        return result, value

    def adoption_ready(self, *, already_selected=False):
        if not already_selected:
            self.selected_slot()
        update = self.author_update(authority_drafts.draft_authority_update(self.root, self.run,
            phase='adoption', scope='sheet', influence='identity'))
        self.import_update(update, 'decisions/adoption-authority.json')
        value = authored.draft(self.root, self.run, scope='sheet', influence='identity')
        self.assertIsNotNone(value['shared_stop_assessments'])
        self.assertIsNone(value['shared_stop_assessments']['confirmed'])
        self.assertEqual(value['additional_stop_assessments'], [])
        value.update(at='2000-01-02T00:00:00Z', reason='Explicit synthetic sheet identity adoption.')
        value['continuity_decision'].update(character_id='robot', continuity='recurring',
            basis={'path': 'actual-curation.txt', 'locator': 'whole'})
        value['shared_stop_assessments']['confirmed'] = True
        return value

    def apply(self, value):
        f.write(self.root / 'decisions/adoption.json', value)
        return authored.apply(self.root, self.run, decision_file='decisions/adoption.json')

    def test_public_commands_complete_slot_and_sheet_without_existing_grants_or_retyped_bindings(self):
        before = store.event_rows(self.root, self.run)
        original_iterations = studio.read_iteration_records(studio.character_home(self.root, 'robot'))
        def actions(action):
            yield action
            for alternative in action.get('alternatives', []):
                yield from actions(alternative)
        status = self.cli('status', '--run', self.run, '--view', 'full')
        choose = next(item for item in actions(status['runs'][0]['next_action'])
                      if item['command'] == 'draft-authority-update')
        report = self.invoke(choose['argv'] + ['--view', 'full'])
        update = self.author_update(report)
        f.write(self.root / report['draft_file'], update)
        imported = self.invoke(report['next_action']['argv'] + ['--view', 'summary'])
        status = self.invoke(imported['next_action']['argv'] + ['--view', 'full'])
        update_action = status['runs'][0]['authority']['update_action']['argv']
        self.assertEqual(update_action[update_action.index('--phase') + 1], 'selection')
        self.assertEqual(update_action[update_action.index('--candidate') + 1], self.candidate)
        choose = next(item for item in actions(status['runs'][0]['next_action'])
                      if item['command'] == 'draft-acceptance'
                      and item['argv'][item['argv'].index('--scope') + 1] == 'studio-slot')
        report = self.invoke(choose['argv'])
        acceptance_value = c.load(self.root / report['draft_file'])
        acceptance_value['reason'] = 'Explicit synthetic slot selection under the supplied instruction.'
        for item in acceptance_value['stop_assessments']:
            item.update(clear=True, evidence='The retained synthetic instruction covers this exact reviewed fixture and both requested uses.')
        f.write(self.root / report['draft_file'], acceptance_value)
        selected = self.invoke(report['next_action']['argv'])
        blocked = self.cli('draft-adoption', '--run', self.run, '--scope', 'sheet', '--influence', 'identity',
                           '--out', 'decisions/blocked.json', expected=3)
        from test_production_report_view import resolved_action
        action = resolved_action(blocked, blocked['diagnostics'][0]['next_action'])
        report = self.invoke(action['argv'] + ['--view', 'full'])
        update = self.author_update(report)
        basis = update['adoption']
        self.assertEqual((basis['candidate'], basis['review'], basis['selection']),
            (self.candidate, acceptance_value['review'], selected['selection']))
        self.assertEqual((basis['scope'], basis['influence'], basis['character'], basis['slot']),
                         ('sheet', 'identity', 'robot', 'base.front'))
        self.assertEqual([(item['operation'], item['targets']) for item in update['grants']], [('adopt', ['canon:sheet'])])
        f.write(self.root / report['draft_file'], update)
        imported = self.invoke(report['next_action']['argv'] + ['--view', 'summary'])
        status = self.cli('status', '--run', self.run, '--view', 'full')
        workflow.schema_check(status, 'status')
        following = status['runs'][0]['adoption_actions'][0]
        self.assertEqual(following['command'], 'draft-adoption')
        self.assertEqual(following['argv'], imported['next_action']['argv'])
        self.assertEqual(status['runs'][0]['next_action']['argv'], following['argv'])
        resumed = self.cli('status', '--run', self.run, '--view', 'summary')
        self.assertEqual(resumed['next_action']['command'], 'draft-adoption')
        self.assertEqual(resumed['next_action']['argv'], following['argv'])
        self.assertTrue(resumed['next_action']['requires_author_input'])
        update_action = status['runs'][0]['authority']['update_action']['argv']
        for option, expected in (('--phase', 'adoption'), ('--scope', 'sheet'), ('--influence', 'identity')):
            self.assertEqual(update_action[update_action.index(option) + 1], expected)
        self.invoke(following['argv'])
        status = self.cli('status', '--run', self.run, '--view', 'full')
        self.assertEqual([item['command'] for item in status['runs'][0]['adoption_actions']], ['adopt'])
        value = c.load(self.root / following['draft'])
        self.assertEqual(value['shared_stop_assessments']['assessments'], [
            {**acceptance_value['stop_assessments'][0], 'condition': self.current_authority().document['stop_conditions'][0]['text']}])
        self.assertEqual(value['additional_stop_assessments'], [])
        self.assertIsNone(value['shared_stop_assessments']['confirmed'])
        value['shared_stop_assessments']['confirmed'] = True
        value.update(at='2000-01-02T00:00:00Z', reason='The synthetic instruction separately approves this canonical use.')
        value['continuity_decision'].update(character_id='robot', continuity='recurring',
            basis={'path': 'actual-curation.txt', 'locator': 'whole'})
        f.write(self.root / following['draft'], value)
        result = self.cli('adopt', '--run', self.run, '--file', following['draft'])
        self.assertEqual(result['data']['result']['status'], 'sheet-bound')
        rows = store.event_rows(self.root, self.run)
        curation = [row for row in rows[len(before):] if row['event'] == 'authorization']
        self.assertEqual([row['data']['request']['operation'] for row in curation], ['select', 'adopt'])
        self.assertNotEqual(curation[0]['data']['request']['grant'], curation[1]['data']['request']['grant'])
        self.assertNotEqual(curation[0]['data']['request']['reason'], curation[1]['data']['request']['reason'])
        self.assertEqual(curation[0]['data']['request']['stop_assessments'], curation[1]['data']['request']['stop_assessments'])
        self.assertNotEqual(curation[0]['data']['files'], curation[1]['data']['files'])
        self.assertFalse({'candidate', 'execution-claim', 'upload', 'send', 'image-output'} &
                         {row['event'] for row in rows[len(before):]})
        self.assertTrue({row['event'] for row in rows[len(before):]} <=
            {'authorization', 'selection', 'slot-acceptance', 'completion', 'adoption-claim', 'operation-start', 'adoption-result'})
        self.assertEqual([item['iteration_id'] for item in original_iterations],
                         [item['iteration_id'] for item in studio.read_iteration_records(studio.character_home(self.root, 'robot'))])
        (self.root / following['draft']).unlink()
        status = self.cli('status', '--run', self.run, '--view', 'full')
        workflow.schema_check(status, 'status')
        self.assertEqual([item['command'] for item in status['runs'][0]['adoption_actions']], ['adopt'])
        self.assertEqual(status['runs'][0]['adoption_actions'][0]['claim'], result['adoption_claim'])

    def test_catalog_authority_continuation_retains_scope_influence_and_registration(self):
        f.write(self.root / 'actual-curation.txt', self.instruction + ' The same synthetic instruction also permits '
            'catalog identity registration of this selected fixture in the designated fixture pack.')
        self.selected_slot()
        record = {'id': 'curation-catalog-fixture', 'label': 'Curation fixture', 'curation_status': 'curated',
            'category': 'species', 'prompt': 'a fictional test character', 'domains': ['shared'],
            'tags': ['fixture', 'character'],
            'search_terms': [{'phrase': 'curation fixture', 'facet': 'species', 'weight': 1.0, 'source': 'author'}],
            'scaffold': {'family': 'direct-geometry-required', 'confidence': 'fallback'}}
        f.write(self.root / 'decisions/catalog-record.json', record)
        destination = Path(self.temp.name) / 'catalog-reference-pack'
        update = self.author_update(authority_drafts.draft_authority_update(self.root, self.run,
            phase='adoption', scope='catalog', influence='identity',
            registration_file='decisions/catalog-record.json', pack_dir=destination))
        imported = self.import_update(update, 'decisions/catalog-authority.json')
        status = execution.status(self.root, self.run)
        workflow.schema_check(status, 'status')
        following = status['runs'][0]['adoption_actions'][0]
        self.assertEqual(following['argv'], imported['next_action']['argv'])
        for argv in (following['argv'], status['runs'][0]['authority']['update_action']['argv']):
            for option, expected in (('--scope', 'catalog'), ('--influence', 'identity'),
                ('--registration-record', 'decisions/catalog-record.json'), ('--pack-dir', str(destination.resolve()))):
                self.assertEqual(argv[argv.index(option) + 1], expected)
        self.assertFalse(destination.exists())

    def test_unreadable_authority_keeps_run_evidence_and_its_owned_readiness_diagnostic(self):
        self.adoption_ready()
        before = store.event_rows(self.root, self.run)
        refusal = ProductionError('AUTHORITY_STATE_CORRUPT', 'Synthetic damaged authority state.', phase='integrity')
        with patch.object(store, 'read_authority', side_effect=refusal):
            status = execution.status(self.root, self.run)
        self.assertFalse(status['ok'])
        self.assertEqual(status['runs'][0]['readiness'], 'blocked')
        self.assertEqual(status['runs'][0]['integrity'], 'intact')
        self.assertIn('AUTHORITY_STATE_CORRUPT', {item['code'] for item in status['runs'][0]['readiness_diagnostics']})
        self.assertEqual(status['runs'][0]['adoption_actions'], [])
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_unclaimed_authorization_does_not_hide_the_imported_pending_use(self):
        value = self.adoption_ready()
        f.write(self.root / 'decisions/unclaimed-adoption.json', value)
        _, request, _, _ = authored._expand(self.root, workflow.read_run(self.root, self.run), value)
        workflow.authorize_value(self.root, self.run, request, evidence_files=['decisions/unclaimed-adoption.json'])
        before = store.event_rows(self.root, self.run)
        self.assertFalse(any(item['event'] == 'adoption-claim' for item in before))
        status = execution.status(self.root, self.run)
        self.assertEqual(status['runs'][0]['next_action']['command'], 'draft-adoption')
        self.assertTrue(status['runs'][0]['next_action']['requires_author_input'])
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_unconfirmed_shared_judgment_and_operation_specific_false_do_not_authorize(self):
        value = self.adoption_ready()
        before = store.event_rows(self.root, self.run)
        value['shared_stop_assessments']['confirmed'] = None
        with self.assertRaises(ProductionError) as caught:
            self.apply(value)
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_REQUIRED')
        value['shared_stop_assessments']['confirmed'] = True
        incomplete = {**copy.deepcopy(value), 'shared_stop_assessments': None}
        with self.assertRaises(ProductionError) as caught:
            self.apply(incomplete)
        self.assertEqual(caught.exception.diagnostic.code, 'AUTHORIZATION_REQUIRED')
        value['additional_stop_assessments'] = [{**value['shared_stop_assessments']['assessments'][0],
            'clear': False, 'evidence': 'The synthetic operator has an adoption-only unresolved condition.'}]
        with self.assertRaisesRegex(ValueError, 'active or unassessed'):
            self.apply(value)
        self.assertEqual(store.event_rows(self.root, self.run), before)
        value['additional_stop_assessments'][0].update(clear=True, evidence='Separate explicit evidence resolves the adoption-specific condition.')
        self.apply(value)
        request = workflow.find(store.event_rows(self.root, self.run), 'authorization')['data']['request']
        self.assertEqual(request['stop_assessments'][0]['evidence'], value['additional_stop_assessments'][0]['evidence'])

    def test_changing_only_authority_digest_cannot_reuse_old_stop_definitions(self):
        value = self.adoption_ready()
        authority = copy.deepcopy(self.current_authority().document)
        authority['stop_conditions'][0]['text'] = 'Stop until the changed synthetic condition is reassessed.'
        self.import_authority(authority)
        value['authority_sha256'] = authored.authority_basis(self.current_authority(), value['grant'], value['scope'])
        before = store.event_rows(self.root, self.run)
        with self.assertRaises(ProductionError) as caught:
            self.apply(value)
        self.assertEqual(caught.exception.diagnostic.code, 'ADOPTION_DECISION_CHANGED')
        self.assertEqual(store.event_rows(self.root, self.run), before)
        fresh = authored.draft(self.root, self.run, scope='sheet', influence='identity')
        self.assertIsNone(fresh['shared_stop_assessments'])
        self.assertFalse(fresh['additional_stop_assessments'][0]['clear'])
        self.assertEqual(fresh['additional_stop_assessments'][0]['evidence'], '')

    def test_added_noncommon_stop_stays_unanswered_and_ends_the_old_proposal(self):
        value = self.adoption_ready()
        authority = copy.deepcopy(self.current_authority().document)
        authority['stop_conditions'].append({'id': 'adoption-only',
            'text': 'Stop until the separate canonical-use instruction is assessed.'})
        self.import_authority(authority)
        value['authority_sha256'] = authored.authority_basis(self.current_authority(), value['grant'], value['scope'])
        with self.assertRaises(ProductionError) as caught:
            self.apply(value)
        self.assertEqual(caught.exception.diagnostic.code, 'ADOPTION_DECISION_CHANGED')
        fresh = authored.draft(self.root, self.run, scope='sheet', influence='identity')
        self.assertIsNone(fresh['shared_stop_assessments'])
        self.assertEqual([item['id'] for item in fresh['additional_stop_assessments']], ['actual-scope', 'adoption-only'])
        self.assertTrue(all(item['clear'] is False and item['evidence'] == '' for item in fresh['additional_stop_assessments']))

    def test_a_new_actual_review_ends_shared_judgment_applicability(self):
        self.selected_slot(halt_before_completion=True)
        value = self.adoption_ready(already_selected=True)
        latest = workflow.latest_review(store.event_rows(self.root, self.run), self.candidate)
        review = copy.deepcopy(workflow.read_run(self.root, self.run).evidence.document(latest['data']['files'][0]['sha256']))
        review['conclusion'] = 'A changed actual synthetic review needs a new selection decision.'
        f.write(self.root / 'new-review.json', review)
        workflow.review(self.root, self.run, 'new-review.json')
        before = store.event_rows(self.root, self.run)
        with self.assertRaises(ProductionError) as caught:
            self.apply(value)
        self.assertEqual(caught.exception.diagnostic.code, 'SELECTION_REVIEW_CHANGED')
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def assert_changed_authority(self, change):
        value = self.adoption_ready()
        authority = copy.deepcopy(self.current_authority().document)
        if change == 'instruction':
            f.write(self.root / 'changed-instruction.txt', 'Changed synthetic instruction requires a fresh judgment.')
            authority['evidence'] = {'path': 'changed-instruction.txt', 'locator': 'whole'}
        else:
            operation = 'select' if change == 'selection-authority' else 'adopt'
            grant = next(item for item in authority['grants'] if operation in item['operations'])
            grant['mode'] = 'delegated'
        self.import_authority(authority)
        value['authority_sha256'] = authored.authority_basis(self.current_authority(), value['grant'], value['scope'])
        before = store.event_rows(self.root, self.run)
        with self.assertRaises(ProductionError) as caught:
            self.apply(value)
        self.assertEqual(caught.exception.diagnostic.code, 'ADOPTION_DECISION_CHANGED')
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_changed_instruction_cannot_be_rebased_by_hash(self):
        self.assert_changed_authority('instruction')

    def test_changed_selection_authority_cannot_be_rebased_by_hash(self):
        self.assert_changed_authority('selection-authority')

    def test_changed_adoption_authority_cannot_be_rebased_by_hash(self):
        self.assert_changed_authority('adoption-authority')

    def test_shared_basis_detects_destination_scope_and_candidate_edits(self):
        original = self.adoption_ready()
        for field, replacement in (('candidate', '0' * 64), ('review', '0' * 64), ('selection', '0' * 64),
                                   ('slot', 'canon.alternate'), ('influence', 'pose-camera'), ('scope', 'catalog')):
            with self.subTest(field=field):
                value = copy.deepcopy(original)
                value['shared_stop_assessments']['basis'][field] = replacement
                before = store.event_rows(self.root, self.run)
                with self.assertRaises(ProductionError) as caught:
                    self.apply(value)
                self.assertEqual(caught.exception.diagnostic.code, 'ADOPTION_DECISION_CHANGED')
                self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_adoption_update_rechecks_destination_and_predecessor_without_any_effect(self):
        import studio_placement
        self.selected_slot()
        update = self.author_update(authority_drafts.draft_authority_update(self.root, self.run,
            phase='adoption', influence='identity'))
        placement = studio_placement.draft(self.root, 'robot', self.row['iteration_id'], 'canon.changed')
        placement.update(by=fixture.ACTOR, at='2026-11-11T04:00:00Z',
            reason='Explicit synthetic placement correction after authority drafting.')
        studio_placement.reassign(self.root, placement)
        before = store.event_rows(self.root, self.run)
        held = self.current_authority().event
        with self.assertRaises(ProductionError) as caught:
            self.import_update(update, 'decisions/stale-adoption-authority.json')
        self.assertEqual(caught.exception.diagnostic.pointer, '$.adoption')
        self.assertEqual(self.current_authority().event, held)
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_actual_owner_allowance_stays_a_nonpassing_review_after_adoption(self):
        original = workflow.latest_review(store.event_rows(self.root, self.run), self.candidate)
        review = copy.deepcopy(workflow.read_run(self.root, self.run).evidence.document(original['data']['files'][0]['sha256']))
        hard = next(item for item in self.task['criteria'] if item['strength'] == 'hard')['id']
        check = next(item for item in review['checks'] if item['criterion'] == hard)
        check.update(verdict='fail', reason='Explicit synthetic assessed discrepancy retained for owner allowance.')
        review['unresolved'] = ['Explicit synthetic unresolved matter accepted for this use only.']
        f.write(self.root / 'allowance-review.json', review)
        reviewed = workflow.review(self.root, self.run, 'allowance-review.json')
        f.write(self.root / 'actual-curation.txt', self.instruction + ' The synthetic principal also explicitly accepts '
            'the assessed failure of criterion ' + hard + ' and unresolved entry zero for these uses only.')
        owner = {'evidence': {'path': 'actual-curation.txt', 'locator': 'whole'}, 'criteria': [hard],
            'unresolved_indices': [0], 'reason': 'The synthetic principal explicitly accepts these named findings for both uses.'}
        self.selected_slot(owner_allowance=owner)
        value = self.adoption_ready(already_selected=True)
        self.apply(value)
        current = workflow.latest_review(store.event_rows(self.root, self.run), self.candidate)
        self.assertEqual(current, reviewed)
        self.assertEqual(next(item for item in current['data']['review']['checks'] if item['criterion'] == hard)['verdict'], 'fail')
        self.assertEqual(current['data']['review']['unresolved'], review['unresolved'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
