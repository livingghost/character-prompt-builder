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
