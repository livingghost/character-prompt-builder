#!/usr/bin/env python3
"""Two adopted identities retain separate authority when delivered on one image."""
from __future__ import annotations
import contextlib
import copy
import io
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import execution_contract as c
import studio_reference as sr
import studio_reference_fixtures as fixture
import prepare_generation_references as refs
import visual_continuity as vc
from build_generation_payload import materialize_cli_reference_bundle


class StudioBoardTests(unittest.TestCase):
    def setUp(self):
        self.case=fixture.adopted_case(self)
        self.root=self.case.root
        self.first=sr.current_source(self.root,'robot',self.case.row['slot'])
        self.second=fixture.adopt_second(self.case,'companion',work_id='C02')
        self.out=self.root/'paired-refs';self.out.mkdir()
        self.spec=c.load(self.root/'spec.json')
        self.spec['subjects']=[{'id':'first','kind':'robot','description':'Synthetic first subject.'},
                               {'id':'second','kind':'robot','description':'Synthetic second subject.'}]

    def prepared(self):
        return refs.prepare_references([{'role':'identity','source':self.first}, {'role':'identity','source':self.second}],
                model='cpb-synthetic-image', output_dir=self.out/'board', transport_mode='single-board', max_side=512)

    def visual(self,prepared):
        return vc.from_decisions({'first':'recurring','second':'recurring'},production_spec=self.spec,prepared=prepared,
            root=self.root,characters={'first':'robot','second':'companion'},work_ids={'first':'C01','second':'C02'})

    def archive(self,prepared):
        root=self.out/'package';root.mkdir()
        sealed,_=materialize_cli_reference_bundle(prepared,model='cpb-synthetic-image',source_root=self.root,
                                                 staging_root=root,companion_name='package.references')
        return root,sealed

    def test_same_pixels_do_not_merge_two_subjects_or_approvals(self):
        self.assertEqual(self.first['sha256'],self.second['sha256'])
        self.assertNotEqual(self.first['proof_sha256'],self.second['proof_sha256'])
        prepared=self.prepared();visual=self.visual(prepared)
        report=vc.require(visual,production_spec=self.spec,prepared=prepared,root=self.root)
        self.assertEqual([row['character_id'] for row in report['identity_bindings']],['C01','C02'])
        self.assertEqual([row['attachment_number'] for row in report['identity_bindings']],[1,1])
        self.assertNotEqual(report['identity_bindings'][0]['region_pixels'],report['identity_bindings'][1]['region_pixels'])

    def test_one_attachment_limit_counts_board_not_sources(self):
        original=refs.resolve_model_record('cpb-synthetic-image')
        model=copy.deepcopy(original[1]);model['max_reference_images']=1
        with patch('prepare_generation_references.resolve_model_record',return_value=(original[0],model)):
            prepared=self.prepared()
            self.assertEqual(len(prepared['selected_references']),2)
            self.assertIsNotNone(prepared['single_board'])
            with self.assertRaisesRegex(ValueError,'max_reference_images'):
                refs.prepare_references([{'role':'identity','source':self.first},{'role':'identity','source':self.second}],
                    model='cpb-synthetic-image',output_dir=self.out/'multiple')

    def test_wrong_subject_for_an_identical_image_is_rejected(self):
        prepared=self.prepared();visual=self.visual(prepared)
        visual['subjects']['first']['identity_refs'][0]['reference_number']=2
        with self.assertRaisesRegex(ValueError,'Studio character'):
            vc.require(visual,production_spec=self.spec,prepared=prepared,root=self.root)

    def test_wrong_artifact_or_acceptance_cannot_substitute_same_pixels(self):
        prepared=self.prepared();visual=self.visual(prepared)
        for key in ('artifact_id','proof_sha256'):
            changed=copy.deepcopy(visual);changed['subjects']['first']['identity_refs'][0][key]=self.second[key]
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'exact Studio acceptance'):
                vc.require(changed,production_spec=self.spec,prepared=prepared,root=self.root)

    def test_missing_identity_choice_cannot_hide_existing_recurring_subject(self):
        prepared=self.prepared();visual=self.visual(prepared)
        visual['subjects']['first'].update(continuity='one-off',character_id=None,identity_refs=[])
        with self.assertRaisesRegex(ValueError,'current accepted identity'):
            vc.require(visual,production_spec=self.spec,prepared=prepared,root=self.root)

    def test_board_pixel_or_region_tampering_is_rejected(self):
        prepared=self.prepared()
        changed=copy.deepcopy(prepared);changed['single_board']['panels'][0]['box']['x']+=1
        changed=__import__('state_protocol').finalize_artifact(changed)
        with self.assertRaises(ValueError):refs.validate_prepared_reference_set(changed)
        image=Path(prepared['single_board']['resolved_path']);image.write_bytes(b'Synthetic corrupt board')
        with self.assertRaises(ValueError):refs.validate_prepared_reference_set(prepared)

    def test_board_replays_with_both_proofs_after_originals_are_removed(self):
        prepared=self.prepared();visual=self.visual(prepared);root,sealed=self.archive(prepared)
        self.assertEqual(len(list((root/'package.references/studio').glob('*/proof.json'))),2)
        for character in ('robot','companion'):
            shutil.rmtree(self.root/f'characters/{character}/sheet/.fills')
        refs.validate_prepared_reference_content(sealed,package_root=root)
        vc.verify_studio_bindings(visual,sealed,package_root=root)
        with self.assertRaises((ValueError,OSError)):refs.validate_prepared_reference_set(sealed,package_root=root)

    def test_changing_only_one_current_selection_stops_the_board(self):
        prepared=self.prepared();path=self.root/'characters/companion/sheet/sheet-data.json'
        sheet=c.load(path);sheet['slots'][self.second['slot']]['current']=None
        c.atomic_write_json(path,sheet)
        sr.validate_source(self.first)
        with self.assertRaisesRegex(ValueError,'no current accepted'):refs.validate_prepared_reference_set(prepared)

    def test_selection_cli_reads_ids_and_hashes_for_each_panel(self):
        choices=[{'character':'robot','slot':self.first['slot'],'role':'identity'},
                 {'character':'companion','slot':self.second['slot'],'role':'identity'}]
        c.atomic(self.out/'choices.json',c.encoded(choices))
        args=['--studio',str(self.root),'--studio-selection-file',str(self.out/'choices.json'),
              '--model','cpb-synthetic-image','--transport-mode','single-board','--output-dir',str(self.out/'cli-board'),
              '--out',str(self.out/'prepared.json')]
        from catalog_retrieval import runtime
        from pack_runtime_cli import PackRuntimeContext
        settings=runtime.selected_pack_settings()
        args += PackRuntimeContext(settings,settings.roots).command_arguments()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(refs.main(args),0)
        result=c.load(self.out/'prepared.json')
        self.assertEqual([row['source'] for row in result['selected_references']],[self.first,self.second])


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
