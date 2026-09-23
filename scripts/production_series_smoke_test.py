#!/usr/bin/env python3
"""Exercise explicit synthetic series identities and protected criteria."""
import copy
import tempfile
import unittest
from pathlib import Path
import execution_contract as c
import production_workflow as w
import production_fixtures as fixture
import work_ledger
from pack_manager import generate_uuid7

class SeriesTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        task=work_ledger.begin(self.root,'Synthetic independent production series',['prepare','deliver'])
        (self.root/'delivery.txt').write_text('Synthetic fixture delivery.\n')
        self.task={'task_id':task['task_id'],'route':'development','features':[],'sources':[],
                   'delivery':{'path':'delivery.txt','transport':'authored-rendition','translation_notes':'Synthetic exact text.'},
                   'criteria':[{'id':'identity','strength':'hard','text':'First synthetic criterion.'}],'world_views':[]}
        fixture.task(self.root,self.task)
        a=c.load(self.root/'fixture-authority.json');a['grants'][0]['protected_criteria']=['identity']
        (self.root/'fixture-authority.json').write_bytes(c.encoded(a))
    def prepare(self,name='task.json'):
        (self.root/name).write_bytes(c.encoded(self.task))
        return w.prepare(self.root,name)['run']
    def test_unrelated_series_does_not_compare_criteria(self):
        first=self.prepare();self.task['production_id']=generate_uuid7();self.task['criteria'][0]['text']='Independent second criterion.'
        second=self.prepare('second.json');p=w.load_run(self.root,second)[1]
        self.assertEqual(p['predecessor'],first);self.assertIsNone(p['criteria_predecessor'])
        fixture.handoff(self.root,second,'synthetic operator','manual')
    def test_same_series_compares_before_reserving(self):
        first=self.prepare();self.task['criteria'][0]['text']='Changed protected criterion.'
        second=self.prepare('second.json');p=w.load_run(self.root,second)[1]
        self.assertEqual(p['criteria_predecessor'],first)
        before=w.reservations(self.root,self.task['task_id'])
        with self.assertRaises(ValueError):fixture.handoff(self.root,second,'synthetic operator','manual')
        self.assertEqual(before,w.reservations(self.root,self.task['task_id']))
    def test_interleaved_series_finds_nearest_same_series(self):
        identity=self.task['production_id'];first=self.prepare()
        self.task['production_id']=generate_uuid7();second=self.prepare('second.json')
        self.task['production_id']=identity;third=self.prepare('third.json')
        p=w.load_run(self.root,third)[1]
        self.assertEqual(p['predecessor'],second);self.assertEqual(p['criteria_predecessor'],first)
    def test_renaming_delivery_keeps_series(self):
        first=self.prepare();(self.root/'renamed.txt').write_text('Synthetic fixture delivery.\n')
        self.task['delivery']['path']='renamed.txt';second=self.prepare('renamed-task.json')
        self.assertEqual(w.load_run(self.root,second)[1]['criteria_predecessor'],first)
    def test_revision_decision_cannot_change_series(self):
        run=self.prepare();p=w.load_run(self.root,run)[1];new=copy.deepcopy(self.task);new['production_id']=generate_uuid7()
        with self.assertRaises(ValueError):w.validate_protected_criteria(self.root,p,p['authority']['grants'][0],revised=new)
    def test_missing_identity_is_not_generated(self):
        del self.task['production_id']
        with self.assertRaises(ValueError):self.prepare()
    def test_budget_uses_same_task_across_series(self):
        first=self.prepare();fixture.handoff(self.root,first,'synthetic operator','manual')
        self.task['production_id']=generate_uuid7();second=self.prepare('second.json');fixture.handoff(self.root,second,'synthetic operator','manual')
        self.assertEqual(len(w.reservations(self.root,self.task['task_id'])),2)

if __name__=='__main__':unittest.main()
