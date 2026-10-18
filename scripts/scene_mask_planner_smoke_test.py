#!/usr/bin/env python3
"""Verify pixels, coverage, review binding and immutable mask publication."""
from __future__ import annotations
import copy
import io
from pathlib import Path
import tempfile
import unittest
from PIL import Image, ImageChops
import execution_contract as c
import scene_mask_planner as m
import scene_mask_fixtures as f


class MaskTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.plan=f.pixels(self.root)
    def write(self,name,value):
        (self.root/name).write_bytes(value if isinstance(value,bytes) else c.encoded(value))
    def test_union_contains_both_separate_sleeves(self):
        d=m.compile_plan(self.root,self.plan);self.assertTrue(d['report']['geometry_valid'])
        self.assertEqual(d['mask'].getpixel((7,15)),255);self.assertEqual(d['mask'].getpixel((24,15)),255)
    def test_omitted_selected_sleeve_fails_independent_requirement(self):
        self.plan['selected'].remove('sleeve-a');d=m.compile_plan(self.root,self.plan)
        self.assertFalse(d['report']['geometry_valid']);self.assertIn('REQUIRED_REGION_MISSING',str(d['report']['findings']))
    def test_unresolved_regions_fail(self):
        self.plan['unresolved']=['Unknown sleeve end.'];self.assertFalse(m.compile_plan(self.root,self.plan)['report']['geometry_valid'])
    def test_collision_fails_instead_of_silent_subtraction(self):
        self.plan['regions'][0]['image']=self.plan['regions'][-1]['image']
        self.assertIn('PROTECTED_OVERLAP',str(m.compile_plan(self.root,self.plan)['report']['findings']))
    def test_invalid_build_writes_no_bundle(self):
        self.plan['selected'].remove('sleeve-b');self.write('mask-plan.json',self.plan)
        m.build(self.root,'mask-plan.json','bad');self.assertFalse((self.root/'bad/bundle.json').exists());self.assertTrue((self.root/'bad/report.json').exists())
    def test_inner_feather_preserves_zero_protection(self):
        self.plan['feather']=3;d=m.compile_plan(self.root,self.plan)
        self.assertTrue(d['report']['geometry_valid']);self.assertEqual(m._count(ImageChops.multiply(d['mask'],d['protection'])),0)
        self.assertEqual(d['mask'].getpixel((11,15)),0);self.assertGreater(sum(d['mask'].histogram()[1:255]),0)
    def test_numeric_flags_are_not_coerced(self):
        for bad in [True,'3',float('inf'),float('nan'),-1]:
            with self.subTest(bad=bad):
                self.plan['feather']=bad
                with self.assertRaises(ValueError):m.compile_plan(self.root,self.plan)
    def test_source_hash_change_fails(self):
        self.write('source.png',b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):m.compile_plan(self.root,self.plan)
    def test_region_hash_change_fails(self):
        self.write('front.png',b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):m.compile_plan(self.root,self.plan)
    def test_region_dimensions_fail(self):
        Image.new('L',(31,32),255).save(self.root/'front.png');self.plan['regions'][0]['image']['sha256']=c.digest((self.root/'front.png').read_bytes())
        with self.assertRaisesRegex(ValueError,'dimensions'):m.compile_plan(self.root,self.plan)
    def test_rgb_mask_fails(self):
        Image.new('RGB',(32,32),'white').save(self.root/'front.png');self.plan['regions'][0]['image']['sha256']=c.digest((self.root/'front.png').read_bytes())
        with self.assertRaisesRegex(ValueError,'grayscale'):m.compile_plan(self.root,self.plan)
    def test_empty_region_fails(self):
        Image.new('L',(32,32),0).save(self.root/'front.png');self.plan['regions'][0]['image']['sha256']=c.digest((self.root/'front.png').read_bytes())
        with self.assertRaisesRegex(ValueError,'Empty'):m.compile_plan(self.root,self.plan)
    def test_nonbinary_annotation_fails(self):
        Image.new('L',(32,32),127).save(self.root/'front.png');self.plan['regions'][0]['image']['sha256']=c.digest((self.root/'front.png').read_bytes())
        with self.assertRaisesRegex(ValueError,'binary'):m.compile_plan(self.root,self.plan)
    def test_path_traversal_fails(self):
        self.plan['source']['path']='../foreign.png'
        with self.assertRaises((ValueError,FileNotFoundError)):m.compile_plan(self.root,self.plan)
    def test_review_required(self):
        m.build(self.root,'mask-plan.json','a')
        with self.assertRaises(ValueError):m.bind(self.root,bundle_path='a/bundle.json',review_path='a/review-template.json',guidance_path=None,out='binding.json')
    def test_review_all_protected_and_selected_regions(self):
        binding=f.reviewed(self.root,self.plan);r=c.load(self.root/'mask-review.json');r['observations'].pop();self.write('mask-review.json',r)
        binding['review']['sha256']=c.digest((self.root/'mask-review.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'Review every'):m.validate_binding(self.root,binding)
    def test_stale_review_rejected(self):
        binding=f.reviewed(self.root,self.plan);r=c.load(self.root/'mask-review.json');r['bundle_sha256']='f'*64;self.write('mask-review.json',r)
        binding['review']['sha256']=c.digest((self.root/'mask-review.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'another mask'):m.validate_binding(self.root,binding)
    def test_saved_mask_checked_by_pixels(self):
        binding=f.reviewed(self.root,self.plan);bundle=c.load(self.root/'masks/a/bundle.json');Image.new('L',(32,32),255).save(self.root/'masks/a/mask.png')
        bundle['mask']['sha256']=c.digest((self.root/'masks/a/mask.png').read_bytes());self.write('masks/a/bundle.json',bundle);binding['bundle']['sha256']=c.digest((self.root/'masks/a/bundle.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'does not equal'):m.validate_binding(self.root,binding)
    def test_preserve_existing_output(self):
        m.build(self.root,'mask-plan.json','a');old=(self.root/'a/mask.png').read_bytes()
        with self.assertRaises(FileExistsError):m.build(self.root,'mask-plan.json','a')
        self.assertEqual((self.root/'a/mask.png').read_bytes(),old)
    def test_source_unchanged(self):
        old=(self.root/'source.png').read_bytes();f.reviewed(self.root,self.plan);self.assertEqual((self.root/'source.png').read_bytes(),old)
    def test_compare_original_zero(self):
        f.reviewed(self.root,self.plan);r=m.compare(self.root,'mask-binding.json','source.png','compare')
        self.assertEqual(r['changed_pixels_outside_mask'],0);self.assertEqual(r['quality_verdict'],'not-assessed')
    def test_compare_changed_protected_pixel(self):
        f.reviewed(self.root,self.plan);im=Image.open(self.root/'source.png').convert('RGB');im.putpixel((15,3),(0,0,0));im.save(self.root/'candidate.png')
        r=m.compare(self.root,'mask-binding.json','candidate.png','compare');self.assertEqual(r['changed_pixels_outside_mask'],1)
    def test_each_dependency_read_once_per_validation(self):
        binding=f.reviewed(self.root,self.plan);calls=[]
        def read(p):calls.append(p);return (self.root/p).read_bytes()
        m.validate_binding(self.root,binding,read=read);self.assertEqual(len(calls),len(set(calls)))
    def test_guidance_optional(self):
        binding=f.reviewed(self.root,self.plan,guidance=False);self.assertIsNone(binding['guidance']);m.validate_binding(self.root,binding)


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
