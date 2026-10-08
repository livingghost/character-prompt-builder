#!/usr/bin/env python3
"""Deterministic evidence checks on synthetic pixels, without a model or personal data."""
from __future__ import annotations
import colorsys
from pathlib import Path
import tempfile
import unittest
from PIL import Image
import execution_contract as c
import sheet_artifacts as fills
import sheet_review as review
from sheet_artifacts_smoke_test import make_sheet,make_artifact,accepted


def region(**changes):
    return {'id':'orange','hue':[10,60],'saturation':[0.1,1],'value':[0,1],'minimum_pixels':10,'rois':{},**changes}


class MeasurementTests(unittest.TestCase):
    def test_known_hsv_medians_and_counts(self):
        result=review.measure(Image.new('RGB',(20,10),(255,128,0)),region())
        self.assertEqual((result['state'],result['selected_pixel_count']),('measured',200))
        self.assertAlmostEqual(result['median']['h'],128/255*60,places=4)
        self.assertEqual(result['median']['s'],1)

    def test_missing_region_is_not_zero_difference(self):
        result=review.measure(Image.new('RGB',(20,10),(0,0,255)),region())
        self.assertEqual(result['state'],'insufficient-pixels')
        self.assertIsNone(result['median'])
        self.assertEqual(result['selected_pixel_count'],0)

    def test_population_below_minimum_is_missing_evidence(self):
        result=review.measure(Image.new('RGB',(2,2),(255,128,0)),region())
        self.assertEqual(result['selected_pixel_count'],4)
        self.assertIsNone(result['median'])

    def test_transparent_pixels_are_excluded(self):
        result=review.measure(Image.new('RGBA',(20,10),(255,128,0,0)),region())
        self.assertEqual(result['visible_pixel_count'],0)
        self.assertIsNone(result['median'])

    def test_hue_wrap_uses_selected_arc(self):
        image=Image.new('RGB',(10,2))
        for x in range(10):
            for y in range(2):
                image.putpixel((x,y),tuple(round(v*255) for v in colorsys.hsv_to_rgb((355 if x<5 else 5)/360,1,1)))
        result=review.measure(image,region(hue=[350,10]))
        self.assertLess(abs((result['median']['h']+180)%360-180),0.2)

    def test_roi_is_recorded_and_checked(self):
        result=review.measure(Image.new('RGB',(20,20),(255,128,0)),region(),[2,3,10,10])
        self.assertEqual(result['roi'],[2,3,10,10]);self.assertEqual(result['selected_pixel_count'],100)
        with self.assertRaises(ValueError):review.measure(Image.new('RGB',(20,20)),region(),[19,0,10,10])

    def test_invalid_ranges_are_not_silently_repaired(self):
        for changes in ({'hue':[10,10]},{'saturation':[1,0]},{'value':[0,float('nan')]},{'minimum_pixels':0}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                review.measure(Image.new('RGB',(20,20)),region(**changes))


class ReviewArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.sheet=make_sheet(self.root/'sheet');self.anchor=accepted(self.sheet,color=(255,128,0))
        self.candidate=make_artifact(self.sheet,marker='candidate',color=(0,0,255))
        fills.register_candidates(self.sheet,[('canon.primary',self.candidate)])
    def entry(self,artifact,label,head=None):
        return {'sheet':str(self.sheet),'slot':'canon.primary','artifact_id':artifact['artifact_id'],'label':label,'head':head}
    def test_review_writes_hashed_full_head_pages_without_changing_selection(self):
        before=self.sheet.read_bytes()
        result=review.build_review(self.entry(self.anchor,'anchor',[0,0,40,40]),[self.entry(self.candidate,'candidate',[0,0,40,40])],[region()],out_dir=self.root/'review',cell_size=100)
        self.assertEqual(result['decision'],'author-required')
        measured=result['measurements'][0]['candidates'][0]
        self.assertEqual(measured['state'],'insufficient-pixels');self.assertIsNone(measured['delta_from_anchor'])
        for kind in ('full','head'):
            item=result['montages'][kind][0]
            self.assertEqual(c.sha256_file(self.root/'review'/item['path']),item['sha256'])
        self.assertEqual(self.sheet.read_bytes(),before)
        self.assertEqual(result['anchor']['artifact'],self.anchor)
    def test_missing_head_crop_is_explicit_not_inferred(self):
        result=review.build_review(self.entry(self.anchor,'anchor'),[self.entry(self.candidate,'candidate')],[],out_dir=self.root/'review',cell_size=100)
        self.assertIsNone(result['anchor']['head']);self.assertEqual(len(result['montages']['head']),1)
    def test_candidate_cannot_be_used_as_accepted_anchor(self):
        with self.assertRaisesRegex(ValueError,'currently accepted'):
            review.build_review(self.entry(self.candidate,'anchor'),[self.entry(self.anchor,'candidate')],[],out_dir=self.root/'review')
    def test_label_roi_mismatch_stops_before_publication(self):
        with self.assertRaisesRegex(ValueError,'unknown artwork'):
            review.build_review(self.entry(self.anchor,'anchor'),[self.entry(self.candidate,'candidate')],[region(rois={'typo':[0,0,20,20]})],out_dir=self.root/'review')
        self.assertFalse((self.root/'review').exists())


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main()
