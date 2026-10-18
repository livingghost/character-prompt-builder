#!/usr/bin/env python3
"""Synthetic boundary fitting and existing build/bind integration; no live generation."""
from __future__ import annotations
import copy
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageChops
import execution_contract as c
import scene_mask_planner as m
import scene_mask_refinement as r


def rect(size, box):
    im=Image.new('L',size,0);ImageDraw.Draw(im).rectangle(box,fill=255);return im


class RefinementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.size=(96,96)
        self.source=Image.new('RGB',self.size,(220,205,178))
        ImageDraw.Draw(self.source).rectangle((30,20,66,75),fill=(27,35,48))
        self.proposal=rect(self.size,(27,17,69,78))
        self.protect=rect(self.size,(0,0,15,95))
        self.opts=dict(inside=6,outside=6,iterations=3,seed=73)
        self.source_ref=self.put('source.png',self.source)
        self.mask_ref=self.put('garment.png',self.proposal)
        self.protect_ref=self.put('protect.png',self.protect)
        self.plan={'format':m.FORMAT,'source':self.source_ref,'regions':[
            {'id':'garment','role':'garment','image':self.mask_ref,'provenance':'Synthetic proposal.'},
            {'id':'protected','role':'protect','image':self.protect_ref,'provenance':'Synthetic protection.'}],
            'selected':['garment'],'required':['garment'],'feather':0,'unresolved':[]}
        self.plan_ref=self.put('plan.json',self.plan)
        self.spec={'format':r.FORMAT,'plan':self.plan_ref,'regions':[
            {'region':'garment',**self.opts,'foreground':None,'background':None}]}
        self.put('refine.json',self.spec)
    def put(self,name,value):
        raw=m._png(value) if isinstance(value,Image.Image) else c.encoded(value)
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        return {'path':name,'sha256':c.digest(raw)}
    def fit(self,**changes):
        return r.fit_region(self.source,self.proposal,self.protect,**{**self.opts,**changes})
    def test_fits_actual_color_boundary(self):
        mask,info,classes=self.fit()
        expected=rect(self.size,(30,20,66,75))
        self.assertEqual(mask.tobytes(),expected.tobytes())
        self.assertGreater(info['removed_pixels'],0);self.assertEqual(info['protected_overlap_pixels'],0)
        self.assertEqual(info['semantic_acceptance'],'unreviewed')
        self.assertGreater(classes.histogram()[2]+classes.histogram()[3],0)
    def test_constrained_outside_band(self):
        mask,_,_=self.fit(outside=0)
        self.assertEqual(m._count(ImageChops.subtract(mask,self.proposal)),0)
    def test_components_are_not_largest_only(self):
        ImageDraw.Draw(self.source).rectangle((75,23,85,52),fill=(27,35,48))
        ImageDraw.Draw(self.proposal).rectangle((72,21,87,54),fill=255)
        mask,info,_=self.fit(inside=3,outside=2)
        self.assertEqual(info['seeded_components'],2)
        self.assertEqual(mask.getpixel((78,35)),255)
    def test_seedless_fragment_refused(self):
        self.proposal.putpixel((85,85),255)
        with self.assertRaisesRegex(ValueError,'component has no certain'):self.fit()
    def test_foreground_points_retain_fragment(self):
        self.proposal.putpixel((85,85),255)
        fg=Image.new('L',self.size);fg.putpixel((85,85),255)
        mask,info,_=self.fit(foreground=fg)
        self.assertEqual(mask.getpixel((85,85)),255)
        self.assertEqual(info['seeded_components'],2)
    def test_protection_conflict_rejected(self):
        self.protect.putpixel((35,35),255)
        with self.assertRaisesRegex(ValueError,'overlap'):self.fit()
    def test_foreground_outside_band_refused(self):
        fg=Image.new('L',self.size);fg.putpixel((90,90),255)
        with self.assertRaisesRegex(ValueError,'search band'):self.fit(foreground=fg)
    def test_conflicting_sample_refused(self):
        bg=Image.new('L',self.size);bg.putpixel((45,45),255)
        with self.assertRaisesRegex(ValueError,'conflict'):self.fit(background=bg)
    def test_grayscale_samples_rejected(self):
        with self.assertRaisesRegex(ValueError,'binary'):
            self.fit(foreground=Image.new('L',self.size,128))
    def test_invalid_parameters(self):
        for key,value in [('inside',True),('outside',-1),('iterations',0),('seed',2**32),('inside',1.5)]:
            with self.subTest(key=key,value=value):
                with self.assertRaises(ValueError):self.fit(**{key:value})
    def test_dimension_mismatch(self):
        self.source=Image.new('RGB',(97,96))
        with self.assertRaisesRegex(ValueError,'dimensions'):self.fit()
    def test_repeat_same_runtime_same_pixels(self):
        a,_,_=self.fit();b,_,_=self.fit();self.assertEqual(a.tobytes(),b.tobytes())
    def test_no_input_image_modification(self):
        before=self.source.tobytes();self.fit();self.assertEqual(before,self.source.tobytes())
    def test_pipeline_build_and_bind(self):
        report=r.refine(self.root,'refine.json','refined')
        self.assertTrue(report['geometry_valid']);self.assertGreater(report['changed_mask_pixels'],0)
        built=m.build(self.root,'refined/refined-plan.json','bundle')
        self.assertTrue(built['geometry_valid'])
        review=c.load(self.root/'bundle/review-template.json')
        self.assertIsNone(review['verdict'])
        review.update(reviewer='Synthetic verifier',verdict='ready',observations=[
            {'region':'garment','observation':'Synthetic boundary coincides with synthetic object.'},
            {'region':'protected','observation':'Constructed protection has zero edit pixels.'}])
        self.put('review.json',review)
        binding=m.bind(self.root,bundle_path='bundle/bundle.json',review_path='review.json',guidance_path=None,out='binding.json')
        m.validate_binding(self.root,binding)
    def test_existing_output_preserved(self):
        r.refine(self.root,'refine.json','refined')
        before=(self.root/'refined/refined-plan.json').read_bytes()
        with self.assertRaises(FileExistsError):r.refine(self.root,'refine.json','refined')
        self.assertEqual(before,(self.root/'refined/refined-plan.json').read_bytes())
    def test_changed_source_blocks_publication(self):
        self.put('source.png',Image.new('RGB',self.size,'red'))
        with self.assertRaisesRegex(ValueError,'changed'):r.refine(self.root,'refine.json','refined')
        self.assertFalse((self.root/'refined').exists())
    def test_extension_is_not_inferred_from_color(self):
        self.plan['regions'][0]['role']='extension';self.spec['plan']=self.put('plan.json',self.plan);self.put('refine.json',self.spec)
        with self.assertRaisesRegex(ValueError,'existing garments only'):r.refine(self.root,'refine.json','refined')
    def test_path_traversal_refused(self):
        with self.assertRaises(ValueError):r.refine(self.root,'refine.json','../outside')
    def test_duplicate_refinement_refused(self):
        self.spec['regions']*=2;self.put('refine.json',self.spec)
        with self.assertRaisesRegex(ValueError,'repeated'):r.refine(self.root,'refine.json','refined')
        self.assertFalse((self.root/'refined').exists())
    def test_adjacent_part_seam_is_not_erased(self):
        self.source=Image.new('RGB',self.size,(220,205,178))
        draw=ImageDraw.Draw(self.source)
        draw.rectangle((30,20,66,75),fill=(27,35,48))
        draw.rectangle((45,25,50,70),fill=(220,205,178))
        self.plan['source']=self.put('source.png',self.source)
        self.plan['regions'][0]['image']=self.put('garment.png',rect(self.size,(27,17,47,78)))
        self.plan['regions'].insert(1,{'id':'part-b','role':'garment',
            'image':self.put('part-b.png',rect(self.size,(48,17,69,78))),
            'provenance':'Adjacent synthetic part.'})
        self.plan['selected'].append('part-b');self.plan['required'].append('part-b')
        self.spec['plan']=self.put('plan.json',self.plan)
        self.spec['regions'].append({**self.spec['regions'][0],'region':'part-b'})
        self.put('refine.json',self.spec)
        r.refine(self.root,'refine.json','refined')
        plan=c.load(self.root/'refined/refined-plan.json')
        mask=m.compile_plan(self.root,plan)['mask']
        self.assertEqual(mask.getpixel((47,45)),255)
        self.assertEqual(mask.getpixel((48,45)),255)
    def test_unselected_and_extension_regions_unchanged(self):
        extra={'id':'new-cover','role':'extension',
            'image':self.put('extension.png',rect(self.size,(80,10,89,20))),
            'provenance':'Synthetic future garment footprint.'}
        self.plan['regions'].append(extra);self.plan['selected'].append('new-cover')
        self.plan['required'].append('new-cover');self.spec['plan']=self.put('plan.json',self.plan)
        self.put('refine.json',self.spec)
        r.refine(self.root,'refine.json','refined')
        plan=c.load(self.root/'refined/refined-plan.json')
        self.assertEqual(plan['regions'][-1],extra)
    def test_unknown_region_refused(self):
        self.spec['regions'][0]['region']='other';self.put('refine.json',self.spec)
        with self.assertRaisesRegex(ValueError,'Unknown'):r.refine(self.root,'refine.json','refined')


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
