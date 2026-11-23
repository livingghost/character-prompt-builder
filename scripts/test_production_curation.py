"""One actual synthetic instruction carries selection and canonical use."""
from __future__ import annotations

import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import execution_contract as c
import production_case_fixtures as f
import production_curation as curation
import production_operations as workflow
import production_store as store
from production_fixtures import ACTOR
import studio_workspace as studio
import transport_synthetic
import test_production_adoption as baseline
from production_diagnostics import ProductionError


class CurationTests(unittest.TestCase):
    setUpClass = classmethod(baseline.AdoptionTests.setUpClass.__func__)
    setUp = baseline.AdoptionTests.setUp
    import_authority = baseline.AdoptionTests.import_authority
    withdraw_adoption = baseline.AdoptionTests.withdraw_adoption

    def draft(self, scope='sheet'):
        destination = {'scope': scope}
        if scope in {'sheet', 'catalog'}:
            destination['influence'] = 'identity'
        return curation.draft(self.root,
            {'kind': 'production', 'run': self.run, 'candidate': self.candidate}, destination)

    def decide(self, drafted):
        choice = copy.deepcopy(drafted['choices'])
        choice['reason'] = 'The actual synthetic instruction selects and adopts this reviewed fixture image.'
        choice['approval'].update(actor=ACTOR, mode=choice['approval']['mode'] or 'direct',
            evidence={'path': 'adoption-basis.txt', 'locator': 'whole synthetic instruction'})
        for assessment in choice['stop_assessments']:
            assessment.update(clear=True, evidence='The synthetic instruction covers this complete selected use.')
        if 'continuity_decision' in choice:
            choice['continuity_decision'].update(character_id='robot', continuity='recurring',
                                                basis=copy.deepcopy(choice['approval']['evidence']))
        return choice

    def apply(self, drafted, decision=None, name='one-use'):
        return curation.apply(self.root, self.root / 'work' / name,
            decision or self.decide(drafted), binding=drafted['binding'], settings=self.settings)

    def test_draft_separates_semantic_choices_from_generated_binding(self):
        value = self.draft()
        self.assertNotIn('run', value['choices'])
        self.assertNotIn('review', value['choices'])
        self.assertNotIn('image_sha256', value['choices'])
        self.assertEqual(value['choices']['reason'], '')
        self.assertNotIn('at', value['choices']['approval'])
        self.assertEqual(value['binding']['source']['candidate'], self.candidate)

    def test_one_decision_selects_and_adopts_without_generation(self):
        draft = self.draft()
        before = store.event_rows(self.root, self.run)
        with patch.object(transport_synthetic, 'send', side_effect=AssertionError('No new generation')):
            result = self.apply(draft)
            again = self.apply(draft)
        self.assertTrue(result['ok'])
        self.assertTrue(again['recovered'])
        rows = store.event_rows(self.root, self.run)
        self.assertEqual([r['event'] for r in rows[len(before):]],
            ['authorization', 'operation-start', 'selection', 'slot-acceptance', 'completion',
             'authorization', 'adoption-claim', 'operation-start', 'adoption-result'])
        requests = [r['data']['request'] for r in rows[len(before):] if r['event'] == 'authorization']
        self.assertEqual([r['operation'] for r in requests], ['select', 'adopt'])
        self.assertEqual(requests[0]['reason'], requests[1]['reason'])
        self.assertIsNotNone(studio.StudioRead(self.root).sheet('robot')['slots']['base.front']['current'])
        progress = c.load(self.root / 'work/one-use/progress.json')
        self.assertNotIn('continuity_evidence', progress)
        self.assertTrue(curation.verify(self.root, self.root / 'work/one-use', binding=draft['binding'])['verified'])

    def test_shared_instruction_proves_continuity_after_its_mutable_source_changes(self):
        drafted = self.draft()
        decision = self.decide(drafted)
        decision['continuity_decision'].pop('basis')
        original = (self.root / 'adoption-basis.txt').read_bytes()
        self.apply(drafted, decision)
        progress_path = self.root / 'work/one-use/progress.json'
        before_progress = progress_path.read_bytes()
        progress = c.load(progress_path)
        self.assertNotIn('continuity_evidence', progress)
        intent = workflow.find(store.event_rows(self.root, 'curation:' + progress['identity']),
                               'curation-intent', progress['intent'])
        self.assertNotIn('continuity_evidence', intent['data'])
        journal = c.load(self.root / 'characters/robot/adoptions' / (self.row['iteration_id'] + '.json'))
        retained = journal['approval']['continuity_decision']['basis']
        self.assertEqual(retained['sha256'], c.digest(original))
        self.assertEqual(retained['locator'], decision['approval']['evidence']['locator'])
        (self.root / 'adoption-basis.txt').write_text('A later unrelated instruction.\n', encoding='utf-8')
        before = store.event_rows(self.root, self.run)
        self.assertTrue(self.apply(drafted, decision)['recovered'])
        self.assertEqual(progress_path.read_bytes(), before_progress)
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_separate_continuity_instruction_without_captured_proof_is_not_shared(self):
        drafted = self.draft()
        decision = self.decide(drafted)
        (self.root / 'character-decision.txt').write_text('The fixture robot is recurring.\n', encoding='utf-8')
        decision['continuity_decision']['basis'] = {'path': 'character-decision.txt', 'locator': 'whole instruction'}
        before = store.event_rows(self.root, self.run)
        original = curation._validate_choices

        def missing_capture(*args):
            return {'instruction': original(*args)['instruction']}

        with patch.object(curation, '_validate_choices', side_effect=missing_capture):
            with self.assertRaisesRegex(ProductionError, 'retained continuity instruction differs'):
                self.apply(drafted, decision)
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_distinct_continuity_source_survives_interruption_and_mutable_source_changes(self):
        drafted = self.draft()
        decision = self.decide(drafted)
        source = self.root / 'character-decision.txt'
        original = b'The explicit synthetic character decision makes robot recurring.\n'
        source.write_bytes(original)
        decision['continuity_decision']['basis'] = {'path': source.name, 'locator': 'the recurring identity instruction'}
        with patch.object(curation, '_production_apply', side_effect=OSError('Synthetic interruption after intent capture')):
            with self.assertRaises(OSError):
                self.apply(drafted, decision)
        source.write_text('A later independent authoring revision.\n', encoding='utf-8')
        self.apply(drafted, decision)
        journal = c.load(self.root / 'characters/robot/adoptions' / (self.row['iteration_id'] + '.json'))
        retained = journal['approval']['continuity_decision']['basis']
        self.assertEqual(retained['sha256'], c.digest(original))
        self.assertEqual(c.local(self.root, retained['path']).read_bytes(), original)
        self.assertEqual(retained['locator'], decision['continuity_decision']['basis']['locator'])
        self.assertNotEqual(retained['sha256'], c.sha256_file(self.root / 'adoption-basis.txt'))
        before = store.event_rows(self.root, self.run)
        self.assertTrue(self.apply(drafted, decision)['recovered'])
        self.assertEqual(before, store.event_rows(self.root, self.run))

    def test_final_verification_detects_a_materializer_substituting_approval_for_continuity(self):
        import production_adoption
        drafted = self.draft()
        decision = self.decide(drafted)
        (self.root / 'character-decision.txt').write_text('The fixture robot is recurring.\n', encoding='utf-8')
        decision['continuity_decision']['basis'] = {'path': 'character-decision.txt', 'locator': 'whole identity instruction'}
        original = production_adoption.apply

        def wrong_basis(root, run, *, decision_file, **kwargs):
            path = c.local(root, decision_file)
            value = c.load(path)
            value['continuity_decision']['basis'] = {'path': 'adoption-basis.txt', 'locator': 'whole identity instruction'}
            f.write(path, value)
            return original(root, run, decision_file=decision_file, **kwargs)

        with patch.object(production_adoption, 'apply', side_effect=wrong_basis):
            self.apply(drafted, decision)
        with self.assertRaisesRegex(ProductionError, 'formal adoption does not retain'):
            curation.verify(self.root, self.root / 'work/one-use', binding=drafted['binding'])

    def test_current_form_explains_and_retains_separate_continuity_evidence(self):
        drafted = self.draft()
        self.assertEqual(set(drafted['answer_contract']['fields']), set(drafted['choices']))
        self.assertEqual(drafted['answer_contract']['paths_relative_to'], str(self.root))
        self.assertTrue(Path(drafted['answer_contract']['document']).is_file())
        self.assertNotIn('basis', drafted['choices']['continuity_decision'])

    def test_prior_permission_does_not_select_the_current_use_instruction(self):
        drafted = self.draft()
        current = drafted['choices']
        self.assertEqual(current['approval']['evidence'], {'path': '', 'locator': ''})
        prior = drafted['evidence']['prior_authority_instruction']
        self.assertTrue(prior)
        for item in prior:
            raw = Path(item['path']).read_bytes()
            self.assertEqual((item['sha256'], item['bytes']), (c.digest(raw), len(raw)))
            self.assertEqual(item['text_preview'], raw.decode('utf-8')[:512])
        decision = self.decide(drafted)
        decision['approval']['evidence'] = copy.deepcopy(current['approval']['evidence'])
        decision['continuity_decision'].pop('basis')
        before = store.event_rows(self.root, self.run)
        with self.assertRaisesRegex(ValueError, 'instruction locator'):
            self.apply(drafted, decision)
        self.assertEqual(store.event_rows(self.root, self.run), before)
        decision['approval']['evidence'] = {'path': 'adoption-basis.txt', 'locator': 'whole current instruction'}
        self.assertTrue(self.apply(drafted, decision)['ok'])
        journal = c.load(self.root / 'characters/robot/adoptions' / (self.row['iteration_id'] + '.json'))
        basis = journal['approval']['continuity_decision']['basis']
        self.assertEqual(basis['sha256'], c.sha256_file(self.root / 'adoption-basis.txt'))
        self.assertEqual(basis['locator'], 'whole current instruction')

    def test_missing_selection_and_adoption_grants_come_from_one_instruction(self):
        authority = store.authority(self.root, self.task['task_id'])
        for grant in authority['grants']:
            grant['operations'] = [op for op in grant['operations'] if op not in {'select', 'adopt'}]
            grant['targets'] = [target for target in grant['targets'] if target not in {'delivery', 'canon:sheet'}]
        self.import_authority(authority)
        draft = self.draft()
        before = store.event_rows(self.root, 'authority:' + self.task['task_id'])
        result = self.apply(draft)
        self.assertTrue(result['ok'])
        additions = store.event_rows(self.root, 'authority:' + self.task['task_id'])[len(before):]
        self.assertEqual(len(additions), 2)
        self.assertEqual(additions[0]['data']['authority']['evidence'], additions[1]['data']['authority']['evidence'])
        self.assertEqual([g['operations'] for g in additions[-1]['data']['authority']['grants'][-2:]],
                         [['select'], ['adopt']])

    def test_authority_scope_is_visible_before_the_shared_instruction_is_chosen(self):
        authority = store.authority(self.root, self.task['task_id'])
        for grant in authority['grants']:
            grant['operations'] = [op for op in grant['operations'] if op != 'adopt']
            grant['targets'] = [target for target in grant['targets'] if target != 'canon:sheet']
        self.import_authority(authority)
        drafted = self.draft()
        requirements = {item['operation']: item for item in drafted['authority_requirements']}
        self.assertEqual(requirements['select']['targets'], ['delivery'])
        self.assertIsNotNone(requirements['select']['selected_grant'])
        self.assertEqual(requirements['adopt']['targets'], ['canon:sheet'])
        self.assertIsNone(requirements['adopt']['selected_grant'])
        self.assertIn('approval.evidence', requirements['adopt']['required_action'])
        self.assertIn('both', drafted['answer_contract']['fields']['approval'])
        self.assertEqual(drafted['choices']['approval']['evidence'], {'path': '', 'locator': ''})

    def test_uncleared_stop_has_no_formal_effect(self):
        authority = store.authority(self.root, self.task['task_id'])
        authority['stop_conditions'] = [{'id': 'scope', 'text': 'Stop outside the actual synthetic instruction.'}]
        self.import_authority(authority)
        draft = self.draft()
        choice = self.decide(draft)
        choice['stop_assessments'][0]['clear'] = False
        before = store.event_rows(self.root, self.run)
        with self.assertRaises(ValueError):
            self.apply(draft, choice)
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_interruption_after_selection_resumes_same_decision(self):
        import production_adoption
        drafted = self.draft()
        with patch.object(production_adoption, 'apply', side_effect=OSError('Synthetic interruption')):
            with self.assertRaises(OSError):
                self.apply(drafted)
        before = store.event_rows(self.root, self.run)
        self.assertEqual(sum(row['event'] == 'selection' for row in before), 1)
        result = self.apply(drafted)
        self.assertTrue(result['ok'])
        rows = store.event_rows(self.root, self.run)
        self.assertEqual(sum(row['event'] == 'selection' for row in rows), 1)
        self.assertEqual(sum(row['event'] == 'adoption-result' for row in rows), 1)

    def test_completed_retry_does_not_restore_withdrawn_image(self):
        drafted = self.draft()
        self.apply(drafted)
        self.withdraw_adoption()
        sheet = studio.character_home(self.root, 'robot') / 'sheet/sheet-data.json'
        before = sheet.read_bytes()
        self.assertTrue(self.apply(drafted)['recovered'])
        self.assertEqual(sheet.read_bytes(), before)

    def test_changed_review_refuses_old_uncommitted_decision(self):
        drafted = self.draft()
        value = c.load(self.root / 'review.json')
        value['conclusion'] += ' A separately retained observation.'
        f.write(self.root / 'review-new.json', value)
        workflow.review(self.root, self.run, 'review-new.json')
        before = store.event_rows(self.root, self.run)
        with self.assertRaises(ProductionError):
            self.apply(drafted)
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_delivery_only_leaves_canonical_destination_unselected(self):
        result = self.apply(self.draft(scope='delivery-only'))
        self.assertTrue(result['ok'])
        self.assertIsNone(studio.StudioRead(self.root).sheet('robot')['slots']['base.front']['current'])
        self.assertFalse(any(row['event'] == 'adoption-claim' for row in store.event_rows(self.root, self.run)))

    def test_one_assessment_is_recorded_separately_for_selection_and_adoption(self):
        authority = store.authority(self.root, self.task['task_id'])
        authority['stop_conditions'] = [{'id': 'scope', 'text': 'Stop outside the synthetic canonical instruction.'}]
        self.import_authority(authority)
        drafted = self.draft()
        decision = self.decide(drafted)
        self.apply(drafted, decision)
        requests = [row['data']['request'] for row in store.event_rows(self.root, self.run)
                    if row['event'] == 'authorization' and row['data']['request']['operation'] in {'select', 'adopt'}]
        self.assertEqual(requests[0]['stop_assessments'], requests[1]['stop_assessments'])

    def test_later_slot_use_keeps_completed_delivery_scope(self):
        self.apply(self.draft('delivery-only'), name='delivery')
        original = workflow.verify_completion(self.root, self.run, self.task['task_id'])
        drafted = self.draft('studio-slot')
        result = self.apply(drafted, name='slot')
        self.assertTrue(result['ok'])
        verified = curation.verify(self.root, self.root / 'work/slot', binding=drafted['binding'])
        self.assertEqual(verified['current_use'], 'current')
        self.assertEqual(workflow.verify_completion(self.root, self.run, self.task['task_id']), original)

    def imported(self, *, package=False):
        imported_package = None
        if package:
            from generation_payload_builder import generation_input_sha256
            value = c.load(self.root / self.row['package']['path'])
            value['production_binding'] = None
            value['generation_input_sha256'] = generation_input_sha256(value)
            value['generation_contract']['generation_input_sha256'] = value['generation_input_sha256']
            imported_package = self.root / 'independent-import-package.json'
            f.write(imported_package, value)
        value = studio.iterate(self.root, 'robot', 'base.front', self.root / self.row['result']['path'],
            package=imported_package,
            request=None, response=None, note='An independent synthetic import with retained identical pixels.')
        return {'kind': 'imported', 'character': 'robot', 'iteration': value['iteration_id']}

    def imported_draft(self, scope):
        source = self.imported(package=scope in {'sheet', 'catalog'})
        drafted = curation.draft(self.root, source,
            {'scope': scope, **({'influence': 'identity'} if scope in {'sheet', 'catalog'} else {})})
        choice = self.decide(drafted)
        choice['review'].update(observation='The synthetic local PNG is visible.',
            conclusion='This exact imported fixture satisfies the requested synthetic use.')
        return drafted, choice

    def test_imported_slot_use_has_an_exact_independent_receipt(self):
        drafted, choice = self.imported_draft('studio-slot')
        self.apply(drafted, choice)
        checked = curation.verify(self.root, self.root / 'work/one-use', binding=drafted['binding'])
        self.assertEqual(checked['current_use'], 'current')
        row = studio.StudioRead(self.root).iteration('robot', drafted['binding']['source']['iteration'])
        self.assertIn('curation_authorization', row['acceptances'][-1])

    def test_imported_sheet_use_needs_actual_observation(self):
        drafted, choice = self.imported_draft('sheet')
        unanswered = copy.deepcopy(choice)
        unanswered['review']['observation'] = ''
        with self.assertRaises(ValueError):
            self.apply(drafted, unanswered)
        self.apply(drafted, choice)
        checked = curation.verify(self.root, self.root / 'work/one-use', binding=drafted['binding'])
        self.assertEqual(checked['current_use'], 'current')

    def test_imported_sheet_use_retains_its_separate_continuity_instruction(self):
        drafted, choice = self.imported_draft('sheet')
        raw = b'This independent synthetic source establishes robot as recurring.\n'
        (self.root / 'import-continuity.txt').write_bytes(raw)
        choice['continuity_decision']['basis'] = {'path': 'import-continuity.txt', 'locator': 'whole identity instruction'}
        self.apply(drafted, choice)
        checked = curation.verify(self.root, self.root / 'work/one-use', binding=drafted['binding'])
        self.assertEqual(checked['current_use'], 'current')
        iteration = drafted['binding']['source']['iteration']
        journal = c.load(self.root / 'characters/robot/adoptions' / (iteration + '.json'))
        basis = journal['approval']['continuity_decision']['basis']
        self.assertEqual(basis['sha256'], c.digest(raw))
        self.assertEqual(c.local(self.root, basis['path']).read_bytes(), raw)
        self.assertEqual(basis['locator'], choice['continuity_decision']['basis']['locator'])

    def test_new_withdrawal_uses_the_same_plan_boundary(self):
        self.apply(self.draft())
        drafted = self.draft('withdraw')
        result = self.apply(drafted, name='withdraw')
        self.assertTrue(result['ok'])
        checked = curation.verify(self.root, self.root / 'work/withdraw', binding=drafted['binding'])
        self.assertEqual(checked['current_use'], 'withdrawn')

    def test_verification_rejects_tampered_progress_result(self):
        drafted = self.draft()
        self.apply(drafted)
        file = self.root / 'work/one-use/progress.json'
        value = c.load(file)
        value['result']['scope'] = 'delivery-only'
        f.write(file, value)
        with self.assertRaises(ProductionError):
            curation.verify(self.root, file.parent, binding=drafted['binding'])

    def test_partial_claim_reassesses_only_changed_conditions(self):
        import adoption_workflow
        drafted = self.draft()
        with patch.object(adoption_workflow, '_bind_sheet', side_effect=OSError('Synthetic sheet interruption')):
            with self.assertRaises(OSError):
                self.apply(drafted)
        before = store.event_rows(self.root, self.run)
        claim = workflow.find(before, 'adoption-claim')['sha256']
        authority = store.authority(self.root, self.task['task_id'])
        authority['stop_conditions'] = [{'id': 'new-scope', 'text': 'Stop unless the renewed synthetic scope is clear.'}]
        self.import_authority(authority)
        with self.assertRaises(ProductionError):
            self.apply(drafted)
        refreshed = curation.reassess(self.root, self.root / 'work/one-use', binding=drafted['binding'])
        self.assertEqual(refreshed['binding']['resume']['claim'], claim)
        self.assertFalse(refreshed['choices']['stop_assessments'][0]['clear'])
        self.assertNotIn('continuity_decision', refreshed['choices'])
        prior = refreshed['evidence']['prior_use_instruction'][0]
        captured = self.root / 'work/one-use/instruction.txt'
        self.assertEqual(prior['path'], str(captured))
        self.assertEqual(prior['sha256'], c.sha256_file(captured))
        self.assertEqual(refreshed['choices']['approval']['evidence'], {'path': '', 'locator': ''})
        self.assertTrue(self.apply(refreshed)['ok'])
        self.assertTrue(self.apply(refreshed)['recovered'])
        rows = store.event_rows(self.root, self.run)
        self.assertEqual([sum(row['event'] == event for row in rows)
                          for event in ('selection', 'adoption-claim', 'adoption-result')], [1, 1, 1])

    def test_revoked_grant_requires_current_instruction_reassessment(self):
        import production_adoption
        drafted = self.draft()
        with patch.object(production_adoption, 'apply', side_effect=OSError('Synthetic adoption interruption')):
            with self.assertRaises(OSError):
                self.apply(drafted)
        authority = store.authority(self.root, self.task['task_id'])
        authority['grants'][0]['revoked_at'] = '2000-01-01T00:00:00Z'
        self.import_authority(authority)
        before = store.event_rows(self.root, 'authority:' + self.task['task_id'])
        with self.assertRaises(ProductionError):
            self.apply(drafted)
        self.assertEqual(store.event_rows(self.root, 'authority:' + self.task['task_id']), before)
        refreshed = curation.reassess(self.root, self.root / 'work/one-use', binding=drafted['binding'])
        self.assertEqual(refreshed['choices']['approval']['evidence']['path'], '')
        self.assertEqual(set(refreshed['binding']['grants']), {'adopt'})
        f.write(self.root / 'renewed-instruction.txt', 'An explicit new synthetic adoption instruction after the prior revocation.')
        decision = self.decide(refreshed)
        decision['approval']['evidence'] = {'path': 'renewed-instruction.txt', 'locator': 'whole synthetic renewal'}
        self.assertTrue(self.apply(refreshed, decision)['ok'])
        rows = store.event_rows(self.root, self.run)
        self.assertEqual(sum(row['event'] == 'selection' for row in rows), 1)

    def test_completed_receipt_recovers_after_progress_save_interruption(self):
        drafted = self.draft()
        writer = curation._write
        def stop_after_result(path, value):
            if path.name == 'progress.json' and 'result' in value:
                raise OSError('Synthetic interruption after the formal result was committed')
            return writer(path, value)
        with patch.object(curation, '_write', side_effect=stop_after_result):
            with self.assertRaises(OSError):
                self.apply(drafted)
        self.withdraw_adoption()
        before = store.event_rows(self.root, self.run)
        result = self.apply(drafted)
        self.assertTrue(result['recovered'])
        self.assertEqual(result['current_use'], 'withdrawn')
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_imported_readoption_and_old_retry_keep_distinct_approvals(self):
        drafted, decision = self.imported_draft('sheet')
        first = self.apply(drafted, decision)
        self.withdraw_adoption()
        later = curation.draft(self.root, drafted['binding']['source'], drafted['binding']['destination'])
        choice = self.decide(later)
        choice['review'] = copy.deepcopy(decision['review'])
        second = self.apply(later, choice, name='readoption')
        self.assertNotEqual(first['result']['approval'], second['result']['approval'])
        before = studio.StudioRead(self.root).sheet('robot')['slots']['base.front']['current']
        retained = self.apply(drafted, decision)
        self.assertTrue(retained['recovered'])
        self.assertEqual(retained['current_use'], 'withdrawn')
        self.assertEqual(studio.StudioRead(self.root).sheet('robot')['slots']['base.front']['current'], before)

    def catalog_draft(self):
        record = {'id': 'adopted-test-character', 'label': 'Adopted fixture', 'curation_status': 'curated',
            'category': 'species', 'prompt': 'a fictional test character', 'domains': ['shared'],
            'tags': ['fixture', 'character'], 'search_terms': [{'phrase': 'adopted test character', 'facet': 'species',
                'weight': 1.0, 'source': 'author'}], 'scaffold': {'family': 'direct-geometry-required', 'confidence': 'fallback'}}
        f.write(self.root / 'registration.json', record)
        return curation.draft(self.root, {'kind': 'production', 'run': self.run, 'candidate': self.candidate},
            {'scope': 'catalog', 'influence': 'identity', 'registration_file': 'registration.json',
             'pack_dir': str(Path(self.temp.name) / 'registered-pack')})

    def test_catalog_use_derives_only_its_required_scope(self):
        drafted = self.catalog_draft()
        self.assertIsNone(drafted['binding']['grants']['adopt'])
        result = self.apply(drafted)
        self.assertTrue(result['ok'])
        self.assertEqual(result['result']['adoption']['data']['result']['status'], 'catalog-registered')
        checked = curation.verify(self.root, self.root / 'work/one-use', binding=drafted['binding'])
        self.assertEqual(checked['current_use'], 'current')
        grants = store.authority(self.root, self.task['task_id'])['grants']
        self.assertEqual(grants[-1]['operations'], ['adopt'])
        self.assertEqual(grants[-1]['targets'], ['canon:catalog'])

    def test_imported_catalog_use_recovers_the_same_registration_after_interruption(self):
        import adoption_workflow
        from pack_manager import validate_pack
        destination = self.catalog_draft()['destination']
        source = self.imported(package=True)
        drafted = curation.draft(self.root, source, destination)
        choice = self.decide(drafted)
        choice['review'].update(observation='The exact imported fixture PNG is visible.',
            conclusion='The explicit synthetic instruction permits this independent catalog registration.')
        original_record = c.load(self.root / 'registration.json')
        publish = adoption_workflow._registration

        def interrupted_registration(*args, **kwargs):
            publish(*args, **kwargs)
            raise OSError('Synthetic interruption after the catalog pack was published.')

        with patch.object(adoption_workflow, '_registration', side_effect=interrupted_registration):
            with self.assertRaisesRegex(OSError, 'after the catalog pack was published'):
                self.apply(drafted, choice)
        target = Path(destination['pack_dir'])
        before = {path.relative_to(target): path.read_bytes() for path in target.rglob('*') if path.is_file()}
        f.write(self.root / 'registration.json', {**original_record, 'label': 'A later unrelated editable record'})
        f.write(self.root / 'adoption-basis.txt', 'A later unrelated instruction cannot replace captured approval.')
        result = self.apply(drafted, choice)
        self.assertEqual(result['result']['status'], 'catalog-registered')
        self.assertTrue(Path(result['result']['registration']['pack_path']).samefile(target))
        self.assertEqual(before, {path.relative_to(target): path.read_bytes() for path in target.rglob('*') if path.is_file()})
        self.assertTrue(validate_pack(target, require_lock=True).valid)
        canonical = c.load(target / 'records/canonical.json')['records'][0]
        self.assertEqual(canonical, original_record)
        self.assertTrue(self.apply(drafted, choice)['recovered'])
        self.assertEqual(curation.verify(self.root, self.root / 'work/one-use',
            binding=drafted['binding'])['current_use'], 'current')

    def test_catalog_record_changes_before_apply_are_explicit(self):
        drafted = self.catalog_draft()
        record = c.load(self.root / 'registration.json')
        record['prompt'] = 'Changed canonical wording needs its own current decision.'
        f.write(self.root / 'registration.json', record)
        before = store.event_rows(self.root, self.run)
        with self.assertRaises(ProductionError):
            self.apply(drafted)
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_imported_slot_receipt_is_accepted_by_studio_validation(self):
        import validate_studio
        drafted, decision = self.imported_draft('studio-slot')
        self.apply(drafted, decision)
        self.assertEqual(validate_studio.validate(self.root), [])

    def test_several_eligible_grants_require_one_explicit_number_per_operation(self):
        authority = store.authority(self.root, self.task['task_id'])
        extra = copy.deepcopy(authority['grants'][0])
        extra['id'] = 'another-current-grant'
        authority['grants'].append(extra)
        self.import_authority(authority)
        drafted = self.draft()
        self.assertEqual(drafted['choices']['grant_choices'], {'select': None, 'adopt': None})
        before = store.event_rows(self.root, 'authority:' + self.task['task_id'])
        with self.assertRaises(ValueError):
            self.apply(drafted)
        decision = self.decide(drafted)
        decision['grant_choices'] = {'select': 2, 'adopt': 2}
        decision['approval'].update(actor=None, mode=None)
        self.assertTrue(self.apply(drafted, decision)['ok'])
        self.assertEqual(store.event_rows(self.root, 'authority:' + self.task['task_id']), before)
        authorizations = [row['data']['request'] for row in store.event_rows(self.root, self.run)
                          if row['event'] == 'authorization' and row['data']['request']['operation'] in {'select', 'adopt'}]
        self.assertEqual([item['grant'] for item in authorizations], ['another-current-grant', 'another-current-grant'])

    def test_uncommitted_source_cannot_withdraw_another_exact_origin(self):
        original = self.draft()
        self.apply(original)
        imported = self.imported(package=True)
        with self.assertRaises(ProductionError):
            curation.draft(self.root, imported, {'scope': 'withdraw'})

    def test_raw_import_catalog_requirements_expose_package_owner(self):
        imported = self.imported()
        with self.assertRaises(ProductionError) as caught:
            curation.draft(self.root, imported, {'scope': 'sheet', 'influence': 'identity'})
        self.assertEqual(caught.exception.diagnostic.code, 'ADOPTION_PACKAGE_REQUIRED')
        self.assertIn('attach-package', caught.exception.diagnostic.required_action)

    def test_sheet_artifact_uses_its_existing_owner_for_adoption_and_withdrawal(self):
        import sheet_artifacts as fills
        imported = self.imported(package=True)
        row = studio.StudioRead(self.root).iteration('robot', imported['iteration'])
        fills.from_iteration(self.root, 'robot', row)
        sheet_path = 'characters/robot/sheet/sheet-data.json'
        candidates = fills._read(self.root / sheet_path)['slots']['base.front']['candidates']
        artifact = next(item for item in candidates if
            fills.verify_artifact(item, (self.root / sheet_path).parent)['origin'].get('iteration_id') == imported['iteration'])
        source = {'kind': 'sheet', 'sheet': sheet_path, 'slot': 'base.front', 'artifact': artifact['artifact_id']}
        drafted = curation.draft(self.root, source, {'scope': 'sheet', 'influence': 'identity'})
        decision = self.decide(drafted)
        decision['review'].update(observation='The exact immutable imported PNG is visible.',
            conclusion='The synthetic instruction adopts this existing sheet candidate.')
        self.assertTrue(self.apply(drafted, decision)['ok'])
        self.assertEqual(curation.verify(self.root, self.root / 'work/one-use', binding=drafted['binding'])['current_use'], 'current')
        withdrawn = curation.draft(self.root, source, {'scope': 'withdraw'})
        self.assertTrue(self.apply(withdrawn, name='withdraw')['ok'])
        self.assertEqual(curation.verify(self.root, self.root / 'work/withdraw', binding=withdrawn['binding'])['current_use'], 'withdrawn')
        fresh = curation.draft(self.root, source, {'scope': 'sheet', 'influence': 'identity'})
        fresh_choice = self.decide(fresh)
        fresh_choice['review'] = copy.deepcopy(decision['review'])
        self.assertTrue(self.apply(fresh, fresh_choice, name='readopt-sheet')['ok'])
        self.assertEqual(curation.verify(self.root, self.root / 'work/withdraw', binding=withdrawn['binding'])['current_use'], 'superseded')

    def test_owner_completion_recovers_after_revocation_without_another_effect(self):
        drafted = self.draft()
        owner = curation._production_apply
        def stop_after_owner(*args, **kwargs):
            owner(*args, **kwargs)
            raise OSError('Synthetic interruption after the owners completed')
        with patch.object(curation, '_production_apply', side_effect=stop_after_owner):
            with self.assertRaises(OSError):
                self.apply(drafted)
        authority = store.authority(self.root, self.task['task_id'])
        authority['grants'][0]['revoked_at'] = '2000-01-01T00:00:00Z'
        self.import_authority(authority)
        before = store.event_rows(self.root, self.run)
        self.assertTrue(self.apply(drafted)['ok'])
        self.assertEqual(store.event_rows(self.root, self.run), before)

    def test_explicit_review_exception_keeps_the_actual_failed_verdict(self):
        review = c.load(self.root / 'review.json')
        criterion = review['checks'][0]['criterion']
        review['checks'][0].update(verdict='fail', reason='An actual synthetic observation reports this fixture exception.')
        review['unresolved'] = ['The synthetic owner must decide whether this visible exception is acceptable.']
        f.write(self.root / 'review-exception.json', review)
        recorded = workflow.review(self.root, self.run, 'review-exception.json')
        drafted = self.draft()
        before = store.event_rows(self.root, self.run)
        with self.assertRaises(ProductionError) as missing:
            self.apply(drafted)
        self.assertEqual(missing.exception.diagnostic.code, 'OWNER_ACCEPTANCE_REQUIRED')
        self.assertEqual(store.event_rows(self.root, self.run), before)
        decision = self.decide(drafted)
        decision['owner_acceptance'] = {'criteria': [criterion], 'unresolved': review['unresolved']}
        f.write(self.root / 'adoption-basis.txt', 'An explicit synthetic instruction accepts this recorded failed criterion '
            'and unresolved finding for this exact canonical use. This is a test fixture only.')
        self.assertTrue(self.apply(drafted, decision)['ok'])
        self.assertEqual(workflow.latest_review(store.event_rows(self.root, self.run), self.candidate), recorded)
        row = studio.StudioRead(self.root).iteration('robot', self.row['iteration_id'])
        self.assertEqual(row['evaluation'], 'nonconforming')

    def test_distinct_existing_actors_and_modes_keep_separate_operation_identity(self):
        authority = store.authority(self.root, self.task['task_id'])
        adopt = copy.deepcopy(authority['grants'][0])
        adopt.update(id='canonical-curator', actor='SYNTHETIC CANONICAL CURATOR - NOT USER CONSENT',
                     mode='delegated', operations=['adopt'], targets=['canon:sheet'],
                     request_scope=None, submission_validation_modes=[])
        authority['grants'][0]['operations'].remove('adopt')
        authority['grants'][0]['targets'].remove('canon:sheet')
        authority['grants'].append(adopt)
        self.import_authority(authority)
        drafted = self.draft()
        self.assertEqual(set(drafted['choices']['approval']), {'evidence'})
        self.assertEqual(drafted['acting_authority']['select']['actor'], ACTOR)
        self.assertEqual(drafted['acting_authority']['adopt']['actor'], adopt['actor'])
        decision = copy.deepcopy(drafted['choices'])
        decision['reason'] = 'The same synthetic instruction authorizes delivery selection and canonical use by their distinct named roles.'
        decision['approval']['evidence'] = {'path': 'adoption-basis.txt', 'locator': 'complete synthetic instruction'}
        decision['continuity_decision'].update(character_id='robot', continuity='recurring')
        self.assertTrue(self.apply(drafted, decision)['ok'])
        requests = {row['data']['request']['operation']: row['data']['request']
                    for row in store.event_rows(self.root, self.run) if row['event'] == 'authorization'
                    and row['data']['request']['operation'] in {'select', 'adopt'}}
        self.assertEqual(requests['select']['actor'], ACTOR)
        self.assertEqual(requests['adopt']['actor'], adopt['actor'])
        journal = c.load(studio.character_home(self.root, 'robot') / 'adoptions' / (self.row['iteration_id'] + '.json'))
        self.assertEqual(journal['approval']['by'], adopt['actor'])

    def test_standalone_sheet_import_keeps_its_owner_and_readopts_from_history(self):
        import sheet_artifacts as fills
        from sheet_artifacts_smoke_test import make_artifact
        path = self.root / 'characters/robot/sheet/sheet-data.json'
        artifact = make_artifact(path, marker='standalone-curation')
        fills.register_candidates(path, [('base.front', artifact)])
        source = {'kind': 'sheet', 'sheet': path.relative_to(self.root).as_posix(),
                  'slot': 'base.front', 'artifact': artifact['artifact_id']}
        self.assertEqual(curation.resolve_source(self.root, source), source)
        drafted = curation.draft(self.root, source, {'scope': 'sheet'})
        decision = self.decide(drafted)
        decision['review'].update(observation='The retained synthetic PNG is visible.',
            conclusion='The synthetic instruction chooses this standalone source.')
        self.apply(drafted, decision)
        withdrawal = curation.draft(self.root, {key: value for key, value in source.items() if key != 'artifact'},
                                   {'scope': 'withdraw'})
        self.apply(withdrawal, name='withdraw')
        fresh = curation.draft(self.root, source, {'scope': 'sheet'})
        second = self.decide(fresh)
        second['review'] = decision['review']
        self.apply(fresh, second, name='readopt')
        current = fills._read(path)['slots']['base.front']['current']
        self.assertEqual(current['artifact']['artifact_id'], artifact['artifact_id'])
        retained = self.apply(drafted, decision)
        self.assertEqual(retained['current_use'], 'withdrawn')
        self.assertEqual(fills._read(path)['slots']['base.front']['current'], current)

    def test_changed_local_decision_cannot_replace_the_saved_actor(self):
        import adoption_workflow
        drafted, decision = self.imported_draft('sheet')
        with patch.object(adoption_workflow, 'adopt', side_effect=OSError('Synthetic interruption before adoption')):
            with self.assertRaises(OSError):
                self.apply(drafted, decision)
        file = self.root / 'work/one-use/local-decision.json'
        retained = c.load(file)
        changed = copy.deepcopy(retained)
        changed['by'] = 'different-unapproved-actor'
        c.atomic(file, c.encoded(changed), replace=True)
        sheet = studio.character_home(self.root, 'robot') / 'sheet/sheet-data.json'
        before = sheet.read_bytes()
        with self.assertRaises(ProductionError) as caught:
            self.apply(drafted, decision)
        self.assertEqual(caught.exception.diagnostic.code, 'ADOPTION_DECISION_CHANGED')
        self.assertEqual(caught.exception.diagnostic.as_dict()['file'], 'work/one-use/local-decision.json')
        self.assertNotIn('result', c.load(self.root / 'work/one-use/progress.json'))
        self.assertEqual(sheet.read_bytes(), before)
        c.atomic(file, c.encoded(retained), replace=True)
        result = self.apply(drafted, decision)
        self.assertTrue(result['ok'])
        self.assertEqual(result['result']['approval']['by'], decision['approval']['actor'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
