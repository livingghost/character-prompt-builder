#!/usr/bin/env python3
"""Check explicit synthetic subjects without inferring them from prose."""
import copy
import tempfile
import unittest
from pathlib import Path
import execution_contract as c
import visual_continuity as v

class SubjectTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.root=Path(t.name)
        (self.root/'basis.txt').write_text('Synthetic single-subject exploration. Not a user approval.\n', encoding='utf-8')
        self.basis=v.file_ref(self.root,'basis.txt',locator='whole')
    def subject(self,continuity='one-off',character=None):
        return {'continuity':continuity,'character_id':character,'studio_character':None,'identity_refs':[]}
    def visual(self,subjects,purpose='image'):
        return {'purpose':purpose,'basis':self.basis,'subjects':subjects}
    def check(self,value):
        v.validate_content(value,{'subjects':[{'id':x} for x in value['subjects']]})
    def test_empty_non_sheet(self): self.check(self.visual({}))
    def test_single_undecided(self): self.check(self.visual({'subject-a':self.subject('undecided')}))
    def test_multiple_undecided(self):
        with self.assertRaises(ValueError): self.check(self.visual({'subject-a':self.subject('undecided'),'subject-b':self.subject()}))
    def test_missing_continuity(self):
        s=self.subject();del s['continuity']
        with self.assertRaises(ValueError):self.check(self.visual({'subject-a':s}))
    def test_recurring_needs_character(self):
        with self.assertRaises(ValueError):self.check(self.visual({'subject-a':self.subject('recurring')}))
    def test_multiple_recurring_needs_identity(self):
        with self.assertRaises(ValueError):self.check(self.visual({'subject-a':self.subject('recurring','CHAR-A'),'subject-b':self.subject()}))
    def test_one_off_pair(self):self.check(self.visual({'subject-a':self.subject(),'subject-b':self.subject()}))
    def test_sheet_is_one_subject(self):
        with self.assertRaises(ValueError):self.check(self.visual({'subject-a':self.subject(),'subject-b':self.subject()},'sheet-panel'))
    def test_empty_sheet(self):
        with self.assertRaises(ValueError):self.check(self.visual({},'sheet-panel'))
    def test_unknown_continuity(self):
        with self.assertRaises(ValueError):self.check(self.visual({'subject-a':self.subject('unknown')}))
    def test_identity_array_required(self):
        s=self.subject();s['identity_refs']='identity'
        with self.assertRaises(ValueError):self.check(self.visual({'subject-a':s}))
    def test_source_hash_is_exact(self):
        value=self.visual({'subject-a':self.subject()});(self.root/'basis.txt').write_text('Changed synthetic source.', encoding='utf-8')
        with self.assertRaises(ValueError):v.check_file(self.root,value['basis'],basis=True)
    def test_locator_does_not_infer_subjects(self):
        value=self.visual({'subject-a':self.subject('undecided')});value['basis']['locator']='A multilingual document about two figures; literal selector only.'
        self.check(value)
    def test_arbitrary_display_words_do_not_change_set(self):
        value=self.visual({'two figures and an overview':self.subject('undecided')})
        self.check(value)

class DecisionTests(unittest.TestCase):
    """Stated decisions become a recorded basis and the same record a person would write."""
    def setUp(self):
        import studio
        from prepare_generation_references import empty_stateless_reference_set
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.root=studio.init(Path(t.name)/'studio','decision-tests','Synthetic decisions')
        studio.add_character(self.root,'C01','')
        self.spec={'subjects':[{'id':'subject-a'}]};self.prepared=empty_stateless_reference_set()
    def decide(self,decisions,**kwargs):
        return v.from_decisions(decisions,production_spec=self.spec,prepared=self.prepared,root=self.root,**kwargs)
    def test_one_off_equals_hand_written_record(self):
        record=self.decide({'subject-a':'one-off'})
        self.assertTrue(record['basis']['path'].startswith('work/continuity/'))
        self.assertEqual(c.load(self.root/record['basis']['path'])['subjects'],{'subject-a':{'continuity':'one-off','studio_character':None}})
        hand={'purpose':'image','basis':{'path':record['basis']['path'],'locator':'whole'},
              'subjects':{'subject-a':{'continuity':'one-off','character_id':None,'studio_character':None,'identity_refs':[]}}}
        self.assertEqual(record,v.build_record(hand,production_spec=self.spec,prepared=self.prepared,root=self.root))
        self.assertEqual(record,self.decide({'subject-a':'one-off'}))
    def test_every_subject_needs_one_decision(self):
        for decisions in ({},{'subject-a':'one-off','subject-b':'one-off'},{'other':'one-off'}):
            with self.subTest(decisions=decisions),self.assertRaises(ValueError):self.decide(decisions)
    def test_unknown_decision_refused(self):
        with self.assertRaises(ValueError):self.decide({'subject-a':'maybe'})
    def test_recurring_names_its_studio_character(self):
        with self.assertRaisesRegex(ValueError,'studio character'):self.decide({'subject-a':'recurring'})
        record=self.decide({'subject-a':'recurring'},characters={'subject-a':'C01'})
        self.assertEqual((record['subjects']['subject-a']['character_id'],record['subjects']['subject-a']['studio_character']),('C01','C01'))
        record=self.decide({'subject-a':'recurring'},characters={'subject-a':'C01'},work_ids={'subject-a':'CHR-1'})
        self.assertEqual(record['subjects']['subject-a']['character_id'],'CHR-1')
    def test_character_for_unknown_subject_refused(self):
        with self.assertRaises(ValueError):self.decide({'subject-a':'one-off'},characters={'other':'C01'})
    def test_changed_decision_record_refused(self):
        record=self.decide({'subject-a':'one-off'});path=self.root/record['basis']['path']
        path.write_bytes(path.read_bytes().replace(b'one-off',b'recurring'))
        with self.assertRaises(ValueError):v.require(record,production_spec=self.spec,prepared=self.prepared,root=self.root)
        with self.assertRaisesRegex(ValueError,'changed'):self.decide({'subject-a':'one-off'})

if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
