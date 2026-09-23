#!/usr/bin/env python3
"""Actual pixel operations and production authority/repair boundaries."""
from __future__ import annotations
import copy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
import execution_contract as c
import image_edit as edit
import production_workflow as w
import production_fixtures as fixture
import work_ledger


def png(size=(12, 8), color=(20, 40, 60, 255)):
    stream=io.BytesIO(); Image.new('RGBA',size,color).save(stream,format='PNG'); return stream.getvalue()


class ImageEditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        task=work_ledger.begin(self.root,'Synthetic image operations',['prepare','deliver'])
        self.put('source.png',png());self.put('overlay.png',png((2,2),(200,0,0,255)));self.put('delivery.txt','Create the specified synthetic plate.')
        self.task={'task_id':task['task_id'],'route':'development','features':[],
          'sources':[{'id':name,'path':name+'.png','role':'world','locator':'whole','disposition':'applied','reason':'Synthetic test source.'} for name in ('source','overlay')],
          'delivery':{'path':'delivery.txt','transport':'authored-rendition','translation_notes':'Synthetic only.'},
          'criteria':[{'id':'pixels','strength':'hard','text':'Observed pixel structure.'}],'world_views':[]}
        fixture.task(self.root,self.task,artifact='image');self.task['criteria'][0]['evidence']='image'
        self.put('task.json',self.task);self.run=w.prepare(self.root,'task.json')['run'];fixture.handoff(self.root,self.run,'pixel editor','manual')
        self.plan={'input_sha256':w.load_run(self.root,self.run)[1]['input_sha256'],
          'source':self.source('source.png'),'operations':[{'operation':'crop','box':[1,2,7,6]}],
          'output':'art/result.png','targets':['delivery'],'repair':None,'reason':'Synthetic declared realization, not artistic assessment.','limitations':['Test only.']}
        self.put('edit.json',self.plan)
    def put(self,path,value):
        p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(value if isinstance(value,bytes) else value.encode() if isinstance(value,str) else c.encoded(value));return p
    def source(self,path):return {'path':path,'sha256':c.digest(c.read(self.root/path))}
    def intent(self):self.put('edit.json',self.plan);return edit.edit_intent(self.root,self.run,'edit.json')
    def execute(self):
        authorization=fixture.grant(self.root,self.run,self.intent())
        return edit.execute(self.root,self.run,'edit.json',authorization)
    def pixels(self):
        with Image.open(self.root/'art/result.png') as im:return im.copy()
    def observed(self,candidate,verdict='pass',name='review.json',repair=False):
        d=w.draft_review(self.root,self.run,candidate['sha256'])
        d.update(reviewer='SYNTHETIC REVIEWER',observations=[{'evidence':'candidate','locator':{'kind':'whole'},'observation':'Inspected the synthetic pixels.','interpretation':'Technical check only.','limitations':['Not an acting test.']}],conclusion='Synthetic check.')
        d['checks'][0].update(verdict=verdict,observation_indices=[0],reason='Observed fixture.')
        if repair:d['repairs']=[{'id':'crop','decisions':[],'observation_indices':[0],'operation':'Reframe pixels','targets':['delivery'],'reason':'The fixture requires a different frame.'}]
        self.put(name,d);return w.review(self.root,self.run,name)
    def test_crop(self):self.execute();self.assertEqual(self.pixels().size,(6,4))
    def test_resize(self):self.plan['operations']=[{'operation':'resize','width':24,'height':16}];self.execute();self.assertEqual(self.pixels().size,(24,16))
    def test_rotate(self):self.plan['operations']=[{'operation':'rotate','degrees':90,'expand':True,'fill':'#00000000'}];self.execute();self.assertEqual(self.pixels().size,(8,12))
    def test_arbitrary_rotation_canvas(self):
        for angle in (13,-31,42,181,279):
            with self.subTest(angle=angle):
                expect=Image.new('RGBA',(12,8)).rotate(angle,expand=True).size
                self.assertEqual(edit._rotation_size(12,8,angle,True),expect)
    def test_composite(self):
        self.plan['operations']=[{'operation':'composite','source':self.source('overlay.png'),'x':1,'y':2,'opacity':1}]
        self.execute();self.assertEqual(self.pixels().getpixel((1,2)),(200,0,0,255));self.assertEqual(self.pixels().getpixel((0,0)),(20,40,60,255))
    def test_clipped_composite(self):
        self.plan['operations']=[{'operation':'composite','source':self.source('overlay.png'),'x':-1,'y':-1,'opacity':1}]
        self.execute();self.assertEqual(self.pixels().getpixel((0,0)),(200,0,0,255))
    def test_opacity_zero(self):
        self.plan['operations']=[{'operation':'composite','source':self.source('overlay.png'),'x':0,'y':0,'opacity':0}]
        self.execute();self.assertEqual(self.pixels().getpixel((0,0)),(20,40,60,255))
    def test_invalid_crop(self):
        self.plan['operations'][0]['box']=[0,0,100,100]
        with self.assertRaises(ValueError):self.intent()
    def test_bool_dimensions(self):
        self.plan['operations']=[{'operation':'resize','width':True,'height':12}]
        with self.assertRaises(ValueError):self.intent()
    def test_large_dimensions_are_not_a_guessed_allocation_limit(self):
        # Metadata validation only: do not allocate a huge image in the test.
        self.assertEqual(edit.dimensions(100000,100000),(100000,100000))
    def test_more_than_256_declared_operations_are_all_executed(self):
        self.plan['operations']=[{'operation':'resize','width':12,'height':8} for _ in range(300)]
        self.execute()
        self.assertEqual(self.pixels().size,(12,8))
    def test_unknown_operation(self):
        self.plan['operations']=[{'operation':'invent-details'}]
        with self.assertRaises(ValueError):self.intent()
    def test_changed_plan_after_authorization(self):
        grant=fixture.grant(self.root,self.run,self.intent());self.plan['operations'][0]['box']=[0,0,4,4];self.put('edit.json',self.plan)
        with self.assertRaises(ValueError):edit.execute(self.root,self.run,'edit.json',grant)
        self.assertFalse((self.root/'art/result.png').exists())
    def test_edit_requires_its_own_permission(self):
        grant=fixture.grant(self.root,self.run,w.handoff_intent(self.root,self.run,'pixel editor','manual'))
        with self.assertRaises(ValueError):edit.execute(self.root,self.run,'edit.json',grant)
    def test_unpinned_source(self):
        self.put('other.png',png());self.plan['source']=self.source('other.png')
        with self.assertRaises(ValueError):self.intent()
    def test_changed_source(self):
        self.put('source.png',png(color=(0,0,0,255)))
        with self.assertRaises(ValueError):self.intent()
    def test_wrong_input(self):
        self.plan['input_sha256']='f'*64
        with self.assertRaises(ValueError):self.intent()
    def test_never_overwrite_input(self):
        self.plan['output']='source.png'
        with self.assertRaises(ValueError):self.intent()
    def test_never_overwrite_existing(self):
        self.put('art/result.png',b'keep')
        with self.assertRaises(ValueError):self.intent()
        self.assertEqual((self.root/'art/result.png').read_bytes(),b'keep')
    def test_internal_directory_not_output(self):
        self.plan['output']='production/unrelated.png'
        with self.assertRaises(ValueError):self.intent()
    def test_scope_not_contract_edit(self):
        self.plan['targets']=['criterion:pixels']
        with self.assertRaises(ValueError):self.intent()
    def test_render_failure_leaves_claim(self):
        grant=fixture.grant(self.root,self.run,self.intent())
        with patch.object(edit,'_render',side_effect=ValueError('test interruption')):
            with self.assertRaises(ValueError):edit.execute(self.root,self.run,'edit.json',grant)
        with patch.object(edit,'_render',side_effect=AssertionError('must not rerender')):
            with self.assertRaises(ValueError):edit.execute(self.root,self.run,'edit.json',grant)
        self.assertFalse((self.root/'art/result.png').exists())
    def test_repeat_recovers_without_rerender(self):
        grant=fixture.grant(self.root,self.run,self.intent());first=edit.execute(self.root,self.run,'edit.json',grant)
        with patch.object(edit,'_render',side_effect=AssertionError('must not rerender')):
            second=edit.execute(self.root,self.run,'edit.json',grant)
        self.assertEqual(first,second)
    def test_interrupted_publication_recovers_exact_object(self):
        grant=fixture.grant(self.root,self.run,self.intent())
        with patch.object(edit,'_publish',side_effect=OSError('test interruption')):
            with self.assertRaises(OSError):edit.execute(self.root,self.run,'edit.json',grant)
        with patch.object(edit,'_render',side_effect=AssertionError('must not rerender')):
            candidate=edit.execute(self.root,self.run,'edit.json',grant)
        self.assertEqual(candidate['event'],'candidate')
    def test_failed_review_needs_next_step(self):
        candidate=self.execute()
        with self.assertRaisesRegex(ValueError,'repair or unresolved'):self.observed(candidate,'fail')
    def test_unresolved_failure_can_be_recorded(self):
        candidate=self.execute();data=w.draft_review(self.root,self.run,candidate['sha256'])
        self.observed(candidate);data=c.load(self.root/'review.json');data['checks'][0]['verdict']='fail';data['unresolved']=['Need an actual correction decision.'];self.put('failed.json',data)
        self.assertEqual(w.review(self.root,self.run,'failed.json')['event'],'review')
    def test_reviewed_repair_and_completion(self):
        self.put('candidate.png',png());candidate=w.capture(self.root,self.run,'candidate.png','Synthetic plate')
        self.observed(candidate,'fail',repair=True)
        self.plan['source']=self.source('candidate.png');self.plan['repair']={'candidate':candidate['sha256'],'repair':'crop'}
        edited=self.execute();self.assertNotEqual(candidate['sha256'],edited['sha256'])
        with self.assertRaises(ValueError):w.draft_selection(self.root,self.run,edited['sha256'])
        self.observed(edited,name='edited-review.json');selection=w.draft_selection(self.root,self.run,edited['sha256'])
        selection['reason']='Synthetic technical result.';fixture.selection(self.root,self.run,selection);self.put('select.json',selection)
        w.select(self.root,self.run,'select.json');self.assertEqual(w.complete(self.root,self.run)['event'],'completion')
    def test_reviewed_source_cannot_hide_repair(self):
        self.put('candidate.png',png());candidate=w.capture(self.root,self.run,'candidate.png','Synthetic plate');self.observed(candidate,'fail',repair=True)
        self.plan['source']=self.source('candidate.png')
        with self.assertRaisesRegex(ValueError,'explicit latest'):self.intent()
    def test_stale_review_invalidates_edit_permission(self):
        self.put('candidate.png',png());candidate=w.capture(self.root,self.run,'candidate.png','Synthetic plate');self.observed(candidate,'fail',repair=True)
        self.plan['source']=self.source('candidate.png');self.plan['repair']={'candidate':candidate['sha256'],'repair':'crop'};grant=fixture.grant(self.root,self.run,self.intent())
        self.observed(candidate,name='new-review.json')
        with self.assertRaises(ValueError):edit.execute(self.root,self.run,'edit.json',grant)


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
