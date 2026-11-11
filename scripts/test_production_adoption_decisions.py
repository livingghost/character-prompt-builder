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
import production_case_fixtures as f
import production_execution as execution
import production_fixtures as fixture
import production_store as store
import production_workflow as workflow
import studio
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
        self.assertEqual([item['id'] for item in value['stop_assessments']], ['canonical-use'])
        if stop_clear:
            value['stop_assessments'][0].update(clear=True,
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
        self.assertEqual(value['stop_assessments'], [{'id': 'canonical-use',
            'condition': 'Stop unless this retained fixture image remains within the revised instruction.',
            'clear': False, 'evidence': ''}])
        value['reason'] = 'Continue this exact synthetic claim under the explicitly revised fixture instruction.'
        value['stop_assessments'][0].update(clear=True,
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
        self.assertEqual(value['stop_assessments'], [{'id': 'canonical-use',
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
                         [{key: value['stop_assessments'][0][key] for key in ('id', 'clear', 'evidence')}])
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

        def stop_before_result(directory, prepared, rows, event, data):
            if event == 'adoption-result':
                raise OSError('Synthetic interruption after Studio applied the decision')
            return append(directory, prepared, rows, event, data)

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
        authority = store.authority(self.root, self.task['task_id'])
        authority['grants'][0]['revoked_at'] = '2000-01-01T00:00:00Z'
        self.import_authority(authority)
        with self.assertRaises(ProductionError) as caught:
            authored.apply(self.root, self.run, claim_id=claim['sha256'])
        self.assertEqual(caught.exception.diagnostic.code, 'GRANT_REVOKED')
        self.assertFalse(self.journal_path().exists())

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


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
