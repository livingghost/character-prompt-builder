#!/usr/bin/env python3
"""Synthetic current-acceptance references and portable proof verification."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import execution_contract as c
import studio
import studio_reference as sr
import sheet_artifacts as fills
from sheet_artifacts_smoke_test import accepted, make_artifact, decision
from production_fixtures import scratch_home_dir


class StudioSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = studio.init(self.base / 'studio', 'synthetic-source-owner', 'Synthetic source fixture')
        studio.add_character(self.root, 'robot', 'general')
        self.sheet = self.root / 'characters/robot/sheet/sheet-data.json'
        self.artifact = accepted(self.sheet)
        self.source = sr.current_source(self.root, 'robot', 'canon.primary')

    def test_current_source_pins_owner_artifact_and_acceptance(self):
        proof = sr.validate_source(self.source)
        self.assertEqual(self.source['artifact_id'], self.artifact['artifact_id'])
        self.assertEqual(self.source['acceptance_sha256'], c.content_id(c.load(self.sheet)['slots']['canon.primary']['current']))
        self.assertEqual(proof['studio_id'], 'synthetic-source-owner')
        from prepare_generation_references import validate_committed_source
        self.assertEqual(validate_committed_source(self.source), self.source)

    def test_recorded_paths_keep_the_origin_platform_without_a_live_lookup(self):
        self.assertEqual(str(sr._origin_root('C:\\Studio') / self.source['sheet']),
                         'C:\\Studio\\characters\\robot\\sheet\\sheet-data.json')
        self.assertEqual(str(sr._origin_root('/recorded/studio') / self.source['sheet']),
                         '/recorded/studio/characters/robot/sheet/sheet-data.json')
        with self.assertRaises(ValueError): sr._origin_root('relative/studio')

    def test_candidate_is_not_current(self):
        candidate = make_artifact(self.sheet, marker='pending')
        fills.register_candidates(self.sheet, [('pending', candidate)])
        with self.assertRaisesRegex(ValueError, 'no current accepted'):
            sr.current_source(self.root, 'robot', 'pending')

    def test_uppercase_studio_character_id_is_canonical(self):
        # Studio character IDs follow studio.CHARACTER_ID, which allows
        # uppercase (C01); only slots are restricted to lowercase.
        studio.add_character(self.root, 'C01', 'general')
        sheet = self.root / 'characters/C01/sheet/sheet-data.json'
        artifact = accepted(sheet)
        source = sr.current_source(self.root, 'C01', 'canon.primary')
        self.assertEqual(source['artifact_id'], artifact['artifact_id'])
        self.assertEqual(source['character'], 'C01')
        from prepare_generation_references import validate_committed_source
        self.assertEqual(validate_committed_source(source), source)

    def test_replacement_is_rejected_even_when_old_bytes_remain(self):
        accepted(self.sheet, marker='replacement', color=(140,80,30))
        self.assertTrue(Path(self.source['resolved_path']).is_file())
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            sr.validate_source(self.source)

    def test_withdrawn_acceptance_is_rejected(self):
        state = c.load(self.sheet); state['slots']['canon.primary']['current'] = None
        from character_sheet import sheet_status
        state['sheet_status'] = sheet_status(state); c.atomic_write_json(self.sheet, state)
        with self.assertRaisesRegex(ValueError, 'no current accepted'):
            sr.validate_source(self.source)

    def test_same_pixels_with_different_provenance_are_distinct(self):
        newer = accepted(self.sheet, marker='new-provenance')
        self.assertEqual(newer['image']['sha256'], self.source['sha256'])
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            sr.validate_source(self.source)

    def test_same_artifact_readopted_under_new_decision_is_distinct(self):
        accepted(self.sheet, marker='other', color=(70,30,90))
        fills.register_candidates(self.sheet, [('canon.primary', self.artifact)])
        choice = decision(self.sheet, 'canon.primary', self.artifact)
        choice['reason'] = 'Explicit synthetic new decision restores this original.'
        fills.adopt(self.sheet, choice, evidence_root=self.sheet.parent)
        self.assertEqual(sr.current_source(self.root, 'robot', 'canon.primary')['artifact_id'], self.source['artifact_id'])
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            sr.validate_source(self.source)

    def test_unrelated_candidates_and_slots_do_not_invalidate(self):
        pending = make_artifact(self.sheet, marker='unrelated')
        fills.register_candidates(self.sheet, [('parts.detail', pending)])
        accepted(self.sheet, slot='parts.other', marker='other-accepted')
        self.assertEqual(sr.current_source(self.root, 'robot', 'canon.primary'), self.source)
        sr.validate_source(self.source)

    def test_same_pixels_in_another_slot_cannot_substitute(self):
        fills.register_candidates(self.sheet, [('parts.other', self.artifact)])
        fills.adopt(self.sheet, decision(self.sheet, 'parts.other', self.artifact), evidence_root=self.sheet.parent)
        forged = copy.deepcopy(self.source); forged['slot'] = 'parts.other'
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            sr.validate_source(forged)

    def test_another_studio_or_character_cannot_substitute(self):
        for changes in ({'studio_id':'another-studio'}, {'character':'another'}, {'sheet':'characters/other/sheet/sheet-data.json'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                sr.validate_source({**self.source, **changes})

    def test_approval_evidence_mutation_is_rejected(self):
        item = c.load(self.sheet)['slots']['canon.primary']['current']['approval']
        (self.sheet.parent / item['evidence_path']).write_bytes(b'changed evidence')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            sr.validate_source(self.source)

    def test_decision_mutation_is_rejected(self):
        item = c.load(self.sheet)['slots']['canon.primary']['current']['approval']
        path = self.sheet.parent / item['decision_path']
        data = c.load(path); data['by'] = 'Someone else'; c.atomic_write_json(path, data)
        with self.assertRaisesRegex(ValueError, 'approval differs'):
            sr.validate_source(self.source)

    def test_image_mutation_is_rejected(self):
        Path(self.source['resolved_path']).write_bytes(b'changed image')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            sr.validate_source(self.source)

    def test_nonidentity_local_approval_is_not_identity_authority(self):
        with self.assertRaisesRegex(ValueError, 'no explicit Studio identity'):
            sr.identity_source(self.source, root=self.root, character_id='robot')

    def test_archive_survives_original_studio_deletion(self):
        companion = self.base / 'package.references'
        sr.archive_source(self.source, companion)
        shutil.rmtree(self.root)
        proof = sr.validate_source(self.source, active=False, source_archive=companion/'sources')
        self.assertEqual(proof['acceptance']['artifact'], self.artifact)

    def test_archive_proof_and_evidence_mutation_are_rejected(self):
        companion = self.base / 'package.references'
        sr.archive_source(self.source, companion)
        folder = companion / 'studio' / self.source['proof_sha256']
        original = (folder/'proof.json').read_bytes()
        (folder/'proof.json').write_bytes(original.replace(b'synthetic-source-owner', b'forged-source-owner'))
        with self.assertRaises(ValueError): sr.validate_source(self.source, active=False, source_archive=companion/'sources')
        (folder/'proof.json').write_bytes(original)
        item = c.load(self.sheet)['slots']['canon.primary']['current']['approval']
        (folder/'sheet'/item['evidence_path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            sr.validate_source(self.source, active=False, source_archive=companion/'sources')

    def test_repeated_archive_is_idempotent(self):
        companion = self.base / 'package.references'
        sr.archive_source(self.source, companion)
        before = {p.relative_to(companion):p.read_bytes() for p in companion.rglob('*') if p.is_file()}
        sr.archive_source(self.source, companion)
        self.assertEqual(before, {p.relative_to(companion):p.read_bytes() for p in companion.rglob('*') if p.is_file()})

    def test_symlink_source_cannot_escape(self):
        path = Path(self.source['resolved_path']); outside = self.base/'outside.png'
        outside.write_bytes(path.read_bytes()); path.unlink()
        try: path.symlink_to(outside)
        except (OSError, NotImplementedError): self.skipTest('symbolic links unavailable')
        with self.assertRaises(ValueError): sr.validate_source(self.source)

    def test_cli_resolves_real_ids_and_does_not_overwrite(self):
        import contextlib, io
        target = self.base/'source.json'
        args = ['--studio',str(self.root),'--character','robot','--slot','canon.primary','source','--out',str(target)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sr.main(args),0)
            self.assertEqual(sr.main(args),1)
        self.assertEqual(c.load(target),self.source)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    with tempfile.TemporaryDirectory(prefix='cpb-source-test-home-') as home:
        scratch_home_dir(Path(home))
        unittest.main()
