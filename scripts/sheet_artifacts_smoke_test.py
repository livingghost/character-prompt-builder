#!/usr/bin/env python3
"""Self-contained sheet candidates, immutable provenance, author adoption and local fills."""
from __future__ import annotations
import copy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import execution_contract as c
import sheet_artifacts as fills
from character_sheet import validate_sidecar


def make_sheet(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    sidecar = root / 'sheet-data.json'
    c.atomic_write_json(sidecar, {'sheet_status': 'identity-ready',
        'fields': {'identity.name': 'Synthetic character', 'identity.species_domain': 'robot'}, 'tables': {}, 'slots': {}})
    return sidecar


def make_artifact(sheet: Path, *, color=(40, 100, 170), size=(80, 100), marker='first') -> dict:
    image = io.BytesIO(); Image.new('RGB', size, color).save(image, format='PNG')
    package = sheet.parent / (marker + '.package.json')
    c.atomic_write_json(package, {'status': 'ready', 'model': 'synthetic-sheet-model',
        'generation_payload': {'marker': marker}, 'generation_contract': {}, 'generation_input_sha256': c.digest(marker.encode())})
    return fills.publish(sheet.parent, image.getvalue(), kind='generation', recipe={'marker': marker}, package=package,
                         origin={'kind': 'external-import', 'note': 'Synthetic test fixture only.'})


def decision(sheet: Path, slot: str, artifact: dict) -> dict:
    data = fills.draft_adoption(sheet, slot, artifact['artifact_id'])
    evidence = sheet.parent / 'synthetic-author.txt'
    if not evidence.exists(): c.atomic(evidence, b'Synthetic explicit author choice; not real user consent.\n')
    data.update(by='synthetic author', at='2026-10-08T00:00:00Z', reason='Synthetic fixture chooses the stated candidate.',
        evidence={'path': evidence.name, 'sha256': c.sha256_file(evidence), 'locator': 'whole'})
    return data


def accepted(sheet: Path, *, slot='canon.primary', marker='source', color=(40,100,170), size=(80,100)) -> dict:
    artifact = make_artifact(sheet, marker=marker, color=color, size=size)
    fills.register_candidates(sheet, [(slot, artifact)])
    fills.adopt(sheet, decision(sheet, slot, artifact), evidence_root=sheet.parent)
    return artifact


def withdrawal_decision(sheet: Path, slot: str = 'canon.primary') -> dict:
    evidence = sheet.parent / 'synthetic-withdrawal.txt'
    if not evidence.exists():
        c.atomic(evidence, b'Synthetic author ends this exact canonical scope. Not real user consent.\n')
    data = fills.draft_withdrawal(sheet, slot, evidence_path=evidence.name,
                                 evidence_locator='whole', evidence_root=sheet.parent)
    data.update(by='synthetic author', at='2026-10-09T00:00:00Z',
        reason='Synthetic author retains the image while ending its current reference scope.')
    return data


class SheetArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sheet = make_sheet(self.root / 'first')

    def test_candidate_is_not_accepted_or_reference_ready(self):
        artifact = make_artifact(self.sheet)
        before = fills.accepted_sha256(c.load(self.sheet))
        fills.register_candidates(self.sheet, [('canon.primary', artifact)])
        state = c.load(self.sheet)
        self.assertIsNone(state['slots']['canon.primary']['current'])
        self.assertEqual(state['sheet_status'], 'identity-ready')
        self.assertEqual(fills.accepted_sha256(state), before)

    def test_withdrawal_preserves_exact_acceptance_and_evidence_and_retries_once(self):
        artifact = accepted(self.sheet)
        before = c.load(self.sheet)['slots']['canon.primary']['current']
        original_files = {path: c.read(path) for path in self.sheet.parent.glob('.fills/approvals/**/*') if path.is_file()}
        choice = withdrawal_decision(self.sheet)
        result = fills.withdraw(self.sheet, choice, evidence_root=self.sheet.parent)
        repeated = fills.withdraw(self.sheet, choice, evidence_root=self.sheet.parent)
        self.assertTrue(repeated['already_withdrawn'])
        self.assertEqual(repeated['withdrawal'], result['withdrawal'])
        slot = c.load(self.sheet)['slots']['canon.primary']
        self.assertIsNone(slot['current'])
        self.assertEqual(slot['history'], [before])
        self.assertEqual(len(slot['withdrawals']), 1)
        self.assertEqual(fills.verify_withdrawal(slot['withdrawals'][0], self.sheet.parent, 'canon.primary', before), choice)
        self.assertEqual({path: c.read(path) for path in original_files}, original_files)
        fills.verify_artifact(artifact, self.sheet.parent)
        validate_sidecar(c.load(self.sheet), sheet_root=self.sheet.parent, verify_files=True)

    def test_old_withdrawal_retry_cannot_remove_a_new_adoption_of_the_same_artifact(self):
        artifact = accepted(self.sheet)
        old = c.load(self.sheet)['slots']['canon.primary']['current']
        old_decision = c.load(self.sheet.parent / old['approval']['decision_path'])
        ending = withdrawal_decision(self.sheet)
        fills.withdraw(self.sheet, ending, evidence_root=self.sheet.parent)
        fills.reoffer(self.sheet, 'canon.primary', artifact['artifact_id'])
        with self.assertRaisesRegex(ValueError, 'withdrawn'):
            fills.adopt(self.sheet, old_decision, evidence_root=self.sheet.parent)
        renewed = decision(self.sheet, 'canon.primary', artifact)
        renewed.update(at='2026-10-10T00:00:00Z', reason='Synthetic author makes a new adoption of the same retained artwork.')
        fills.adopt(self.sheet, renewed, evidence_root=self.sheet.parent)
        current = c.load(self.sheet)['slots']['canon.primary']['current']
        self.assertNotEqual(c.content_id(current), c.content_id(old))
        fills.withdraw(self.sheet, ending, evidence_root=self.sheet.parent)
        self.assertEqual(c.load(self.sheet)['slots']['canon.primary']['current'], current)

    def test_withdrawal_retry_uses_saved_evidence_after_original_is_removed(self):
        accepted(self.sheet)
        ending = withdrawal_decision(self.sheet)
        first = fills.withdraw(self.sheet, ending, evidence_root=self.sheet.parent)
        (self.sheet.parent / ending['evidence']['path']).unlink()
        repeated = fills.withdraw(self.sheet, ending, evidence_root=self.sheet.parent)
        self.assertTrue(repeated['already_withdrawn'])
        self.assertEqual(first['withdrawal'], repeated['withdrawal'])

    def test_withdrawal_retry_recovers_notification_after_the_canonical_change_committed(self):
        import studio_activity
        accepted(self.sheet)
        ending = withdrawal_decision(self.sheet)
        with patch.object(studio_activity, 'changed', side_effect=OSError('Synthetic interruption after canonical commit.')):
            with self.assertRaises(OSError):
                fills.withdraw(self.sheet, ending, evidence_root=self.sheet.parent)
        self.assertIsNone(c.load(self.sheet)['slots']['canon.primary']['current'])
        first_retry = fills.withdraw(self.sheet, ending, evidence_root=self.sheet.parent)
        second_retry = fills.withdraw(self.sheet, ending, evidence_root=self.sheet.parent)
        self.assertTrue(first_retry['already_withdrawn'])
        self.assertTrue(second_retry['already_withdrawn'])
        events, errors = studio_activity.read_events(studio_activity.scope(self.sheet))
        self.assertEqual(errors, [])
        self.assertEqual(sum(event['event'] == 'sheet-adoption-withdrawn' for event in events), 1)
        self.assertEqual(len(c.load(self.sheet)['slots']['canon.primary']['withdrawals']), 1)

    def test_withdrawal_history_verifies_in_a_copied_sheet_without_the_origin(self):
        import shutil
        accepted(self.sheet)
        fills.withdraw(self.sheet, withdrawal_decision(self.sheet), evidence_root=self.sheet.parent)
        copied = self.root / 'copied'
        shutil.copytree(self.sheet.parent, copied)
        shutil.rmtree(self.sheet.parent)
        validate_sidecar(c.load(copied / 'sheet-data.json'), sheet_root=copied, verify_files=True)
        from sheet_inventory import status
        row = status(copied / 'sheet-data.json')['entries'][0]
        self.assertEqual(row['canonical_status'], 'withdrawn')
        self.assertEqual(row['availability'], 'verified')

    def test_withdrawal_conflicts_with_another_decision_even_for_identical_pixels(self):
        artifact = accepted(self.sheet)
        ending = withdrawal_decision(self.sheet)
        accepted(self.sheet, marker='same-pixels-new-provenance')
        self.assertEqual(c.load(self.sheet)['slots']['canon.primary']['current']['artifact']['image']['sha256'],
                         artifact['image']['sha256'])
        before = c.read(self.sheet)
        with self.assertRaisesRegex(ValueError, 'changed after'):
            fills.withdraw(self.sheet, ending, evidence_root=self.sheet.parent)
        self.assertEqual(c.read(self.sheet), before)

    def test_withdrawal_rechecks_the_exact_target_after_evidence_io(self):
        accepted(self.sheet)
        ending = withdrawal_decision(self.sheet)
        original = fills._safe_directory
        replaced = []
        def replace_during_evidence(root, relative):
            result = original(root, relative)
            if relative.startswith(fills.WITHDRAWALS) and not replaced:
                replaced.append(True)
                accepted(self.sheet, marker='interleaved', color=(90, 70, 30))
            return result
        with patch.object(fills, '_safe_directory', side_effect=replace_during_evidence):
            with self.assertRaisesRegex(ValueError, 'changed while'):
                fills.withdraw(self.sheet, ending, evidence_root=self.sheet.parent)
        slot = c.load(self.sheet)['slots']['canon.primary']
        self.assertEqual(slot['withdrawals'], [])
        self.assertIsNotNone(slot['current'])

    def test_withdrawal_evidence_corruption_is_reported_by_validation_and_inventory(self):
        accepted(self.sheet)
        result = fills.withdraw(self.sheet, withdrawal_decision(self.sheet), evidence_root=self.sheet.parent)
        path = self.sheet.parent / result['withdrawal']['decision']['evidence_path']
        path.write_bytes(b'Changed synthetic withdrawal evidence.')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            validate_sidecar(c.load(self.sheet), sheet_root=self.sheet.parent, verify_files=True)
        from sheet_inventory import status
        row = status(self.sheet)['entries'][0]
        self.assertEqual(row['canonical_status'], 'withdrawn')
        self.assertEqual(row['availability'], 'unavailable')
        import contextlib
        import json
        import sheet_workflow
        ending = self.sheet.parent / result['withdrawal']['decision']['decision_path']
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = sheet_workflow.main(['withdraw', '--sheet', str(self.sheet), '--decision-file', str(ending),
                                       '--evidence-root', str(self.sheet.parent)])
        self.assertEqual(code, 2)
        diagnostic = json.loads(output.getvalue())['diagnostics'][0]
        self.assertEqual(diagnostic['code'], 'ADOPTION_WITHDRAWAL_CORRUPT')
        self.assertEqual(diagnostic['file'], str(path))
        self.assertIn('verified Studio copy', diagnostic['required_action'])

    def test_withdrawal_cli_drafts_only_and_records_the_authored_decision(self):
        import contextlib
        import json
        import sheet_workflow
        accepted(self.sheet)
        target = self.sheet.parent / 'withdrawal.json'
        before = c.read(self.sheet)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = sheet_workflow.main(['draft-withdrawal', '--sheet', str(self.sheet), '--slot', 'canon.primary',
                                       '--out', str(target)])
        self.assertEqual(code, 0)
        self.assertEqual(c.read(self.sheet), before)
        self.assertEqual(c.load(target)['by'], '')
        authored = c.load(target)
        authored.update(by='Synthetic owner', at='2026-11-11T07:00:00Z', reason='Synthetic authority ends this adoption.')
        c.atomic_write_json(target, authored)
        evidence = self.sheet.parent / 'selected-authority.txt'
        c.atomic(evidence, b'Synthetic authority for this withdrawal only. Not user consent.\n')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = sheet_workflow.main(['draft-withdrawal', '--sheet', str(self.sheet), '--slot', 'canon.primary',
                '--out', str(target), '--evidence-path', evidence.name, '--evidence-locator', 'whole instruction',
                '--evidence-root', str(self.sheet.parent)])
        self.assertEqual(code, 0, output.getvalue())
        pinned = c.load(target)
        self.assertEqual(pinned['by'], authored['by'])
        self.assertEqual(pinned['evidence'], {'path': evidence.name, 'locator': 'whole instruction',
                                             'sha256': c.sha256_file(evidence)})
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = sheet_workflow.main(['withdraw', '--sheet', str(self.sheet), '--decision-file', str(target),
                                       '--evidence-root', str(self.sheet.parent)])
        self.assertEqual(code, 0, output.getvalue())
        self.assertTrue(json.loads(output.getvalue())['withdrawn'])

    def test_selected_withdrawal_evidence_cannot_be_silently_repinned(self):
        import contextlib
        import sheet_workflow
        accepted(self.sheet)
        ending = withdrawal_decision(self.sheet)
        target = self.sheet.parent / 'withdrawal.json'
        c.atomic_write_json(target, ending)
        original_draft, original_sheet = c.read(target), c.read(self.sheet)
        evidence = self.sheet.parent / ending['evidence']['path']
        evidence.write_bytes(b'A different synthetic authority statement, not the pinned decision.\n')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = sheet_workflow.main(['draft-withdrawal', '--sheet', str(self.sheet), '--slot', 'canon.primary',
                '--out', str(target), '--evidence-path', evidence.name, '--evidence-locator', ending['evidence']['locator'],
                '--evidence-root', str(self.sheet.parent)])
        self.assertEqual(code, 2)
        self.assertIn('already pins different evidence', output.getvalue())
        self.assertEqual(c.read(target), original_draft)
        with self.assertRaisesRegex(ValueError, 'evidence bytes changed'):
            fills.withdraw(self.sheet, ending, evidence_root=self.sheet.parent)
        self.assertEqual(c.read(self.sheet), original_sheet)

    def test_reject_candidate_removes_it_with_a_reason_and_keeps_the_bytes(self):
        artifact = make_artifact(self.sheet, marker='reject-me')
        fills.register_candidates(self.sheet, [('canon.primary', artifact)])
        result = fills.reject_candidate(self.sheet, 'canon.primary', artifact['artifact_id'],
                                        by='synthetic author', reason='Synthetic rejection fixture.')
        self.assertTrue(result['ok'])
        state = c.load(self.sheet)
        self.assertEqual(state['slots']['canon.primary']['candidates'], [])
        fills.verify_artifact(artifact, self.sheet.parent)
        with self.assertRaisesRegex(ValueError, 'not recorded'):
            fills.reject_candidate(self.sheet, 'canon.primary', artifact['artifact_id'],
                                   by='synthetic author', reason='Twice.')
        again = make_artifact(self.sheet, marker='reject-me')
        self.assertEqual(again['artifact_id'], artifact['artifact_id'])

    def test_image_and_provenance_are_adopted_together(self):
        artifact = accepted(self.sheet)
        state = validate_sidecar(c.load(self.sheet), sheet_root=self.sheet.parent, verify_files=True)
        self.assertEqual(state['sheet_status'], 'reference-ready')
        self.assertEqual(fills.current_artifact(state['slots']['canon.primary']), artifact)

    def test_redo_retains_current_until_explicit_adoption_and_preserves_history(self):
        first = accepted(self.sheet)
        candidate = make_artifact(self.sheet, color=(180, 80, 40), marker='second')
        before = c.load(self.sheet)['slots']['canon.primary']['current']
        signature = fills.accepted_sha256(c.load(self.sheet))
        fills.register_candidates(self.sheet, [('canon.primary', candidate)])
        self.assertEqual(c.load(self.sheet)['slots']['canon.primary']['current'], before)
        self.assertEqual(fills.accepted_sha256(c.load(self.sheet)), signature)
        fills.adopt(self.sheet, decision(self.sheet, 'canon.primary', candidate), evidence_root=self.sheet.parent)
        state = c.load(self.sheet)['slots']['canon.primary']
        self.assertEqual(state['history'], [before])
        self.assertEqual(state['current']['artifact'], candidate)
        self.assertEqual(state['candidates'], [])
        fills.verify_artifact(first, self.sheet.parent)

    def test_candidate_registration_and_adoption_are_idempotent(self):
        artifact = make_artifact(self.sheet)
        fills.register_candidates(self.sheet, [('canon.primary', artifact), ('canon.primary', artifact)])
        approval = decision(self.sheet, 'canon.primary', artifact)
        fills.adopt(self.sheet, approval, evidence_root=self.sheet.parent)
        self.assertTrue(fills.adopt(self.sheet, approval, evidence_root=self.sheet.parent)['already_adopted'])
        self.assertEqual(c.load(self.sheet)['slots']['canon.primary']['history'], [])

    def test_stale_adoption_does_not_replace_newer_current(self):
        accepted(self.sheet)
        second = make_artifact(self.sheet, marker='second')
        third = make_artifact(self.sheet, marker='third')
        fills.register_candidates(self.sheet, [('canon.primary', second), ('canon.primary', third)])
        stale = decision(self.sheet, 'canon.primary', third)
        fills.adopt(self.sheet, decision(self.sheet, 'canon.primary', second), evidence_root=self.sheet.parent)
        with self.assertRaisesRegex(ValueError, 'current artwork changed'):
            fills.adopt(self.sheet, stale, evidence_root=self.sheet.parent)
        self.assertEqual(fills.current_artifact(c.load(self.sheet)['slots']['canon.primary']), second)

    def test_adoption_checks_saved_author_evidence(self):
        artifact = make_artifact(self.sheet)
        fills.register_candidates(self.sheet, [('canon.primary', artifact)])
        approval = decision(self.sheet, 'canon.primary', artifact)
        (self.sheet.parent / 'synthetic-author.txt').write_text('Changed.', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'evidence bytes changed'):
            fills.adopt(self.sheet, approval, evidence_root=self.sheet.parent)

    def test_failed_adoption_write_leaves_current_untouched_and_retry_works(self):
        first = accepted(self.sheet)
        second = make_artifact(self.sheet, marker='second')
        fills.register_candidates(self.sheet, [('canon.primary', second)])
        approval = decision(self.sheet, 'canon.primary', second)
        original = c.atomic_write_json
        def fail(path, value):
            if Path(path) == self.sheet: raise OSError('Synthetic interruption before atomic selection write')
            return original(path, value)
        with patch.object(c, 'atomic_write_json', side_effect=fail), self.assertRaises(OSError):
            fills.adopt(self.sheet, approval, evidence_root=self.sheet.parent)
        self.assertEqual(fills.current_artifact(c.load(self.sheet)['slots']['canon.primary']), first)
        fills.adopt(self.sheet, approval, evidence_root=self.sheet.parent)
        self.assertEqual(fills.current_artifact(c.load(self.sheet)['slots']['canon.primary']), second)

    def test_image_tampering_is_detected(self):
        artifact = accepted(self.sheet)
        (self.sheet.parent / artifact['image']['path']).write_bytes(b'not an image')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            validate_sidecar(c.load(self.sheet), sheet_root=self.sheet.parent, verify_files=True)

    def test_provenance_and_package_tampering_are_detected(self):
        artifact = accepted(self.sheet)
        folder = (self.sheet.parent / artifact['provenance']['path']).parent
        (folder / 'package.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            fills.verify_artifact(artifact, self.sheet.parent)

    def test_verification_cache_does_not_skip_another_observers_sources(self):
        from story_timeline import Inputs
        class Observer:
            __hash__=None
            def __init__(self,inputs):self.inputs=inputs
            def __eq__(self,other):return isinstance(other,Observer)
            def __call__(self,root,relative,load):return self.inputs.read_sheet(root,relative,load)
        artifact=make_artifact(self.sheet)
        first=Inputs(self.root,self.root/'first.html')
        second=Inputs(self.root,self.root/'second.html')
        cache={}
        fills.verify_artifact(artifact,self.sheet.parent,cache=cache,read_source=Observer(first))
        fills.verify_artifact(artifact,self.sheet.parent,cache=cache,read_source=Observer(second))
        self.assertEqual(first.facts(),second.facts())
        self.assertEqual(len(first.facts()),3)
        package=(self.sheet.parent/artifact['provenance']['path']).parent/'package.json'
        package.write_bytes(b'{}')
        third=Inputs(self.root,self.root/'third.html')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            fills.verify_artifact(artifact,self.sheet.parent,cache=cache,read_source=Observer(third))
        changed=next(row for row in third.facts() if row['path']==package.relative_to(self.root).as_posix())
        self.assertEqual(changed['status'],'present');self.assertEqual(changed['sha256'],c.digest(b'{}'))
        with self.assertRaisesRegex(ValueError,'input changed during projection'):first.recheck()

    def test_observed_artifact_refusal_precedes_bytes_and_remains_sheet_scoped(self):
        from story_timeline import Inputs
        artifact=make_artifact(self.sheet)
        path=self.sheet.parent/artifact['image']['path'];raw=path.read_bytes()
        target=self.root/'outside.png';target.write_bytes(raw);path.unlink()
        try:path.symlink_to(target)
        except (OSError,NotImplementedError):self.skipTest('symbolic links unavailable')
        inputs=Inputs(self.root,self.root/'timeline.html')
        with patch.object(c,'read',wraps=c.read) as read:
            with self.assertRaisesRegex(ValueError,'symbolic link'):
                fills.verify_artifact(artifact,self.sheet.parent,read_source=inputs.read_sheet)
            self.assertFalse(any(Path(call.args[0]).resolve()==target for call in read.call_args_list))
        fact=next(row for row in inputs.facts() if row['path']==path.relative_to(self.root).as_posix())
        self.assertEqual(fact['status'],'failed');self.assertIsNone(fact['sha256'])
        self.assertEqual(fact['read_contract']['root'],'first')
        inputs.recheck();path.unlink();path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'input changed during projection'):inputs.recheck()

    def test_artifact_publication_is_immutable_and_idempotent(self):
        first = make_artifact(self.sheet)
        again = make_artifact(self.sheet)
        self.assertEqual(first, again)
        self.assertEqual(len(list((self.sheet.parent / fills.STORE).iterdir())), 1)

    def test_copy_preserves_image_provenance_and_content_id(self):
        artifact = accepted(self.sheet)
        target = make_sheet(self.root / 'second')
        self.assertEqual(fills.copy_artifact(artifact, self.sheet.parent, target.parent), artifact)
        fills.verify_artifact(artifact, target.parent)

    def test_crop_uses_exact_accepted_source_and_remains_a_candidate(self):
        source = accepted(self.sheet)
        artifact = fills.crop(self.sheet, 'canon.primary', 'part.hand', [10, 20, 30, 40], scale=4)
        self.assertEqual((artifact['image']['width'], artifact['image']['height']), (120, 160))
        record = fills.verify_artifact(artifact, self.sheet.parent)
        self.assertEqual(record['sources'], [source])
        self.assertEqual(record['recipe']['crop'], {'x':10,'y':20,'width':30,'height':40})
        self.assertIsNone(c.load(self.sheet)['slots']['part.hand']['current'])

    def test_crop_source_does_not_change_after_source_panel_redo(self):
        source = accepted(self.sheet)
        artifact = fills.crop(self.sheet, 'canon.primary', 'part.hand', [10, 20, 30, 40])
        accepted(self.sheet, marker='source-redo', color=(180,80,40))
        record = fills.verify_artifact(artifact, self.sheet.parent)
        self.assertEqual(record['sources'][0]['artifact_id'], source['artifact_id'])

    def test_crop_requires_accepted_source_and_valid_bounds(self):
        artifact = make_artifact(self.sheet)
        fills.register_candidates(self.sheet, [('canon.primary', artifact)])
        with self.assertRaisesRegex(ValueError, 'no accepted artwork'):
            fills.crop(self.sheet, 'canon.primary', 'part.hand', [0,0,10,10])
        fills.adopt(self.sheet, decision(self.sheet, 'canon.primary', artifact), evidence_root=self.sheet.parent)
        for rectangle in ([0,0,90,90], [-1,0,20,20], [0,0,0,20], [0.0,0,10,10]):
            with self.subTest(rectangle=rectangle), self.assertRaises(ValueError):
                fills.crop(self.sheet, 'canon.primary', 'part.hand', rectangle)

    def test_shared_image_supplies_several_slots_without_transferring_adoption(self):
        source = accepted(self.sheet)
        second = make_sheet(self.root / 'second')
        result = fills.share(self.sheet, 'canon.primary', [(self.sheet,'size.reference'), (second,'size.reference')])
        self.assertFalse(result['adopted'])
        first_artifact, second_artifact = [item['artifact'] for item in result['targets']]
        self.assertEqual(first_artifact, second_artifact)
        self.assertEqual(first_artifact['image']['sha256'], source['image']['sha256'])
        self.assertIsNone(c.load(second)['slots']['size.reference']['current'])
        fills.adopt(second, decision(second,'size.reference',second_artifact), evidence_root=second.parent)
        self.assertIsNone(c.load(self.sheet)['slots']['size.reference']['current'])

    def test_shared_registration_can_be_repeated_after_interruption(self):
        accepted(self.sheet)
        second = make_sheet(self.root / 'second')
        first = fills.share(self.sheet, 'canon.primary', [(second,'size.reference')])
        second_result = fills.share(self.sheet, 'canon.primary', [(second,'size.reference')])
        self.assertEqual(first, second_result)
        self.assertEqual(len(c.load(second)['slots']['size.reference']['candidates']),1)

    def test_declared_scale_uses_measured_height_and_common_baseline(self):
        accepted(self.sheet, size=(80,100))
        second = make_sheet(self.root / 'second')
        accepted(second, size=(90,120))
        entries = [
            {'sheet':str(self.sheet),'slot':'canon.primary','bbox':[0,0,80,100],'height':180,'measurement_top':10,'baseline':90,'label':'A'},
            {'sheet':str(second),'slot':'canon.primary','bbox':[0,0,90,120],'height':185,'measurement_top':10,'baseline':110,'label':'B'}]
        artifact = fills.compose_scale(self.sheet,'size.reference',entries,pixels_per_unit=1)
        record = fills.verify_artifact(artifact,self.sheet.parent)
        self.assertAlmostEqual(record['recipe']['entries'][0]['factor'],180/80)
        self.assertAlmostEqual(record['recipe']['entries'][1]['factor'],185/100)
        self.assertEqual(len(record['sources']),2)
        self.assertIsNone(c.load(self.sheet)['slots']['size.reference']['current'])

    def test_scale_refuses_unmeasured_or_out_of_bounds_source(self):
        accepted(self.sheet)
        entry = {'sheet':str(self.sheet),'slot':'canon.primary','bbox':[0,0,80,100],'height':180,'measurement_top':90,'baseline':10,'label':'A'}
        with self.assertRaisesRegex(ValueError, 'measurement_top'):
            fills.compose_scale(self.sheet,'size.reference',[entry],pixels_per_unit=1)

    def test_symlinked_image_or_store_is_not_followed(self):
        artifact = make_artifact(self.sheet)
        image = self.sheet.parent / artifact['image']['path']
        copied = self.root / 'outside.png'; copied.write_bytes(image.read_bytes()); image.unlink()
        try: image.symlink_to(copied)
        except (OSError, NotImplementedError): self.skipTest('symbolic links unavailable')
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            fills.verify_artifact(artifact,self.sheet.parent)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
