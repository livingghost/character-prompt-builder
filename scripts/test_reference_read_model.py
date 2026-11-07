"""Reference builders retain one read boundary and recheck the next one."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import adoption_workflow as adoption
import execution_contract as c
import feature_workflow_smoke_test as imported_fixture
import prepare_generation_references as references
import runtime_snapshot
import studio
import studio_reference
import visual_continuity as visual


class ReferenceReadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        imported_fixture.FeatureWorkflowTests.setUpClass()
        cls.addClassCleanup(imported_fixture.FeatureWorkflowTests.tearDownClass)

    def setUp(self):
        self.case = imported_fixture.FeatureWorkflowTests(
            'test_01_package_requires_real_settled_record_and_verifies')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.root = self.case.root
        self.rows = []

    def accept(self, color='white', slot='canon.front'):
        row = self.case.iteration(color=color, slot=slot)
        self.case.adopt(row)
        self.rows.append(row)
        return row

    def prepared(self, *, current=False):
        selections = ([{'role': 'identity', 'source': studio_reference.current_source(
            self.root, 'C01', row['slot'])} for row in self.rows] if current
            else adoption.supplied_selection(self.root, 'C01'))
        return references.prepare_references(selections, model=imported_fixture.MODEL_ID,
            output_dir=self.root / ('current' if current else 'supplied'), transport_mode='single-board')

    def build(self, prepared, **kwargs):
        return visual.from_decisions({'C01': 'recurring'}, production_spec={'subjects': [{'id': 'C01'}]},
            prepared=prepared, root=self.root, characters={'C01': 'C01'}, **kwargs)

    def test_each_accepted_package_is_verified_once_for_multiple_identity_choices(self):
        for color, slot in [('red', 'canon.front'), ('green', 'canon.side'), ('blue', 'canon.rear')]:
            self.accept(color, slot)
        prepared = self.prepared()
        from verify_generation_payload import verify_content
        with (patch.object(adoption, '_reference_index', wraps=adoption._reference_index) as index,
              patch('verify_generation_payload.verify_content', wraps=verify_content) as verify,
              patch.object(studio, 'read_iteration_records', wraps=studio.read_iteration_records) as rows):
            result = self.build(prepared)
        self.assertEqual(index.call_count, 1)
        self.assertEqual(verify.call_count, 3)
        self.assertEqual(rows.call_count, 1)
        subject = result['subjects']['C01']
        self.assertEqual(subject['character_id'], 'C01')
        self.assertEqual({(row['slot'], row['iteration_id']) for row in subject['identity_refs']},
                         {(row['slot'], row['iteration_id']) for row in self.rows})
        self.assertEqual({row['reference_number'] for row in subject['identity_refs']}, {1, 2, 3})
        for row in subject['identity_refs']:
            self.assertEqual(row['source_sha256'], prepared['selected_references'][row['reference_number'] - 1]['source']['sha256'])

    def test_unselected_damaged_adoption_still_blocks_continuity(self):
        self.accept('red', 'canon.front')
        prepared = self.prepared()
        unrelated = self.accept('blue', 'canon.rear')
        (self.root / unrelated['package']['path']).write_bytes(b'Synthetic damaged package')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.build(prepared)
        self.assertFalse(adoption.reference_index(self.root, 'C01')['ok'])

    def test_pending_adoption_still_blocks_continuity(self):
        selected = self.accept()
        prepared = self.prepared()
        journal = adoption._journal_path(studio.character_dir(self.root, 'C01'), selected['iteration_id'])
        pending = c.load(journal)
        pending['next_action'] = 'bind-sheet'
        c.atomic_write_json(journal, pending)
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.build(prepared)

    def test_new_build_rechecks_package_bytes_with_same_size_and_timestamp(self):
        row = self.accept()
        prepared = self.prepared()
        self.build(prepared)
        path = self.root / row['package']['path']
        before = path.stat()
        raw = path.read_bytes()
        changed = raw.replace(b'"ready"', b'"other"', 1)
        self.assertNotEqual(changed, raw)
        self.assertEqual(len(changed), len(raw))
        path.write_bytes(changed)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, 'reference workflow is incomplete'):
            self.build(prepared)

    def test_new_build_rechecks_exact_current_acceptance(self):
        self.accept()
        prepared = self.prepared(current=True)
        self.build(prepared)
        self.accept('blue')
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            self.build(prepared)

    def test_returned_package_and_proof_cannot_poison_the_read_model(self):
        row = self.accept()
        read = studio.StudioRead(self.root)
        _, package = read.package(row['package'], verify=True)
        package['model'] = 'not-the-verified-model'
        self.assertEqual(read.package(row['package'], verify=True)[1]['model'], imported_fixture.MODEL_ID)
        source, proof = read.current_reference('C01', row['slot'])
        source['studio_id'] = 'another-studio'
        proof['identity']['character_id'] = 'another-character'
        current_source, current_proof = read.current_reference('C01', row['slot'])
        self.assertEqual(current_source['studio_id'], 'fixture-studio')
        self.assertEqual(current_proof['identity']['character_id'], 'C01')
        self.assertEqual(read.package(row['package'], verify=True)[1], c.load(self.root / row['package']['path']))
        for change in (
            lambda: read.document['characters'].clear(),
            lambda: read.raw_iterations('C01')[0].update(status='rejected'),
            lambda: read.sheet('C01')['slots'][row['slot']].update(current=None),
            lambda: read.journal('C01', row['iteration_id']).update(status='pending'),
            lambda: read.current_reference_view('C01', row['slot'])[1]['identity'].update(character_id='other'),
            lambda: read.reference_index('C01')['bindings'][0].update(next_action='not-current'),
        ):
            with self.assertRaises(TypeError):
                change()
        exported = adoption.reference_index(self.root, 'C01', read=read)
        exported['bindings'][0]['next_action'] = 'changed-export'
        self.assertIsNone(read.reference_index('C01')['bindings'][0]['next_action'])

    def test_source_identity_continuity_and_index_share_one_reference_phase(self):
        for color, slot in [('red', 'canon.front'), ('green', 'canon.side'), ('blue', 'canon.rear')]:
            self.accept(color, slot)
        choices = [{'character': 'C01', 'slot': row['slot'], 'role': 'identity',
                    'subject_uses': [{'subject_id': 'C01', 'use': 'identity', 'priority': 0}]}
                   for row in self.rows]
        from verify_generation_payload import verify_content
        with (runtime_snapshot.public_call(),
              patch.object(studio, 'read_iteration_records', wraps=studio.read_iteration_records) as rows,
              patch.object(studio, 'manifest', wraps=studio.manifest) as manifest,
              patch.object(studio_reference, '_load_current', wraps=studio_reference._load_current) as proof,
              patch('verify_generation_payload.verify_content', wraps=verify_content) as verify,
              patch.object(adoption, '_reference_index', wraps=adoption._reference_index) as index):
            selected = references.resolve_studio_reference_choices(self.root, choices)
            prepared = references.prepare_references(selected, model=imported_fixture.MODEL_ID,
                output_dir=self.root / 'current', transport_mode='single-board')
            visual = self.build(prepared)
            current = adoption.reference_index(self.root, 'C01')
        self.assertEqual(manifest.call_count, 1)
        self.assertEqual(rows.call_count, 1)
        self.assertEqual(proof.call_count, 3)
        self.assertEqual(verify.call_count, 3)
        self.assertEqual(index.call_count, 1)
        self.assertTrue(current['ok'])
        self.assertEqual(len(visual['subjects']['C01']['identity_refs']), 3)
        self.assertEqual([entry['source'] for entry in prepared['selected_references']],
                         [entry['source'] for entry in selected])

    def test_resolver_reacquires_after_owned_mutation_in_the_same_public_call(self):
        row = self.accept()
        reads = studio_reference.ReferenceReads()
        with runtime_snapshot.public_call():
            before = reads.studio(self.root)
            self.assertIs(reads.studio(self.root / 'characters/C01'), before)
            source = studio_reference.current_source(self.root, 'C01', row['slot'], read=before)
            self.accept('blue')
            after = reads.studio(self.root)
            self.assertIsNot(after, before)
            with self.assertRaisesRegex(ValueError, 'no longer matches'):
                studio_reference.validate_source(source, reads=reads)
            current = studio_reference.current_source(self.root, 'C01', row['slot'], read=after)
            self.assertNotEqual(current['artifact_id'], source['artifact_id'])

    def test_reference_resolver_observes_new_transaction_and_fresh_publication(self):
        import production_store as store
        self.accept()
        reads = studio_reference.ReferenceReads()
        with runtime_snapshot.public_call():
            outer = reads.studio(self.root)
            with store.transaction(self.root):
                transaction = reads.studio(self.root)
                self.assertIsNot(transaction, outer)
                self.assertIs(reads.studio(self.root), transaction)
            after_transaction = reads.studio(self.root)
            self.assertIsNot(after_transaction, transaction)
            with runtime_snapshot.public_call(fresh=True):
                fresh = reads.studio(self.root)
                self.assertIsNot(fresh, after_transaction)
                self.assertIs(reads.studio(self.root), fresh)
            self.assertIsNot(reads.studio(self.root), fresh)

    def test_interrupted_mutation_cannot_leave_a_retained_current_reference(self):
        import studio_activity
        row = self.accept()
        reads = studio_reference.ReferenceReads()

        @studio_activity.mutation(receipt=False)
        def interrupted(root):
            path = root / 'characters/C01/sheet/sheet-data.json'
            state = c.load(path)
            state['slots'][row['slot']]['history'].append(state['slots'][row['slot']]['current'])
            state['slots'][row['slot']]['current'] = None
            from character_sheet import sheet_status
            state['sheet_status'] = sheet_status(state)
            c.atomic_write_json(path, state)
            raise OSError('Synthetic interrupted owner after committing its sidecar')

        with runtime_snapshot.public_call():
            read = reads.studio(self.root)
            source = studio_reference.current_source(self.root, 'C01', row['slot'], read=read)
            with self.assertRaisesRegex(OSError, 'Synthetic interrupted owner'):
                interrupted(self.root)
            self.assertIsNot(reads.studio(self.root), read)
            with self.assertRaisesRegex(ValueError, 'no current accepted'):
                studio_reference.validate_source(source, reads=reads)

    def test_read_model_must_belong_to_the_requested_studio(self):
        row = self.accept()
        read = studio.StudioRead(self.root)
        read.current_reference('C01', row['slot'])
        other = studio.init(self.case.work / 'other-studio', 'other', 'Another synthetic Studio')
        with self.assertRaisesRegex(ValueError, 'another root'):
            studio_reference.current_source(other, 'C01', row['slot'], read=read)
        with self.assertRaisesRegex(ValueError, 'another root'):
            adoption.reference_index(other, 'C01', read=read)

    def test_reload_discards_package_proof_and_index_results(self):
        row = self.accept()
        read = studio.StudioRead(self.root)
        self.assertTrue(read.reference_index('C01')['ok'])
        source = studio_reference.current_source(self.root, 'C01', row['slot'], read=read)
        read.package(row['package'], verify=True)
        self.accept('blue')
        read.reload()
        current = studio_reference.current_source(self.root, 'C01', row['slot'], read=read)
        self.assertNotEqual(current['artifact_id'], source['artifact_id'])
        self.assertEqual(read.reference_index('C01')['bindings'][0]['iteration_id'], self.rows[-1]['iteration_id'])
        self.assertEqual(len(read.adoption_rows('C01')), 2)


class ProductionReferenceReadTests(unittest.TestCase):
    def test_live_studio_root_is_resolved_before_identity_check(self):
        import studio_reference_fixtures as production_fixture
        case = production_fixture.adopted_case(self)
        source = studio_reference.current_source(case.root, 'robot', case.row['slot'])
        ref = {'slot': source['slot'], 'artifact_id': source['artifact_id'],
               'proof_sha256': source['proof_sha256'], 'source_sha256': source['sha256']}
        alias = case.root.parent / 'alias-studio'
        work_id = case.approval['continuity_decision']['character_id']
        original = Path.resolve

        def resolve(path, *, strict=False):
            if path == alias:
                return case.root
            return original(path, strict=strict)

        with patch.object(Path, 'resolve', new=resolve):
            proof = visual.studio_identity_binding(ref, source, root=alias,
                character='robot', character_id=work_id)
        self.assertEqual(proof['identity']['character_id'], work_id)

    def test_reference_index_checks_adopted_run_without_loading_unrelated_history(self):
        import production_workflow as workflow
        import studio_reference_fixtures as production_fixture
        case = production_fixture.adopted_case(self)
        root = case.root
        home = studio.character_home(root, 'robot')
        rows = studio.read_iteration_records(home)
        unrelated = copy.deepcopy(rows[0])
        unrelated.update(iteration_id='it-9999', slot='unselected-history', adoption_status='none',
                         production={'run': '1' * 64, 'candidate': '2' * 64})
        studio.write_iterations(home, [*rows, unrelated])
        with patch.object(workflow, 'read_run', wraps=workflow.read_run) as load:
            index = adoption.reference_index(root, 'robot')
        self.assertTrue(index['ok'], index['errors'])
        self.assertEqual(len(index['bindings']), 1)
        self.assertEqual([call.args[1] for call in load.call_args_list], [case.run])
        # Only the stored adoption axis grants an accepted reference. A stale
        # display field on a Production row cannot replace that authority.
        for status in ('none', 'superseded'):
            raw = copy.deepcopy(rows[0])
            raw.update(adoption_status=status, status='accepted')
            c.atomic(home / 'iterations.jsonl', c.encoded(raw) + b'\n', replace=True)
            self.assertEqual(adoption.reference_index(root, 'robot')['bindings'], [])
        studio.write_iterations(home, rows)
        # Resolve the actual registered publication rather than assume its layout.
        import production_store
        registration = production_store.registered_run(root, case.run)
        publication = c.local(root, registration['directory']) / 'prepared.json'
        publication.write_bytes(publication.read_bytes() + b' ')
        index = adoption.reference_index(root, 'robot')
        self.assertFalse(index['ok'])
        self.assertEqual(index['bindings'][0]['next_action'], 'repair-reference')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
