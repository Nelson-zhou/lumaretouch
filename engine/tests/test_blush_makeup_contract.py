# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored UNRUN source contracts. Synthetic arrays are not portrait acceptance.

Run only in the approved local QA environment after building the native artifact.
This file was neither imported nor executed by the source author.
"""
import json
import unittest
from pathlib import Path
import numpy as np
from lumaretouch_engine import blush_makeup_state as S, blush_makeup_project as PROJECT
from lumaretouch_engine.blush_makeup_catalogue import catalogue,material,CATALOGUE_SHA256
from lumaretouch_engine.blush_makeup_native import delta

class BlushIntent(unittest.TestCase):
    def test_original_patterns_are_shapes_not_colours(self):
        rows=catalogue()['patterns'];self.assertEqual(len(rows),12)
        self.assertEqual(tuple(row['id'] for row in rows),S.PATTERNS)
        self.assertEqual(len({json.dumps(row['lobes'],sort_keys=True) for row in rows}),12)
        for row in rows:self.assertGreaterEqual(len(row['recommended']),2)

    def test_neutral_independent_controls_and_saved_limit(self):
        self.assertFalse(S.active(None));value=S.check({**S.neutral(),'strength':.7,'pattern':'lift','colour':'#aa8899'})
        self.assertEqual(value['colour'],'#AA8899');self.assertEqual(value['pattern'],'lift')
        colors=['#000000','#111111','#222222','#333333','#444444','#555555']
        self.assertEqual(S.save_colour(colors,colors[0]),colors)
        with self.assertRaises(ValueError):S.save_colour(colors,'#FFFFFF')
        self.assertEqual(len(S.save_colour(S.remove_colour(colors,colors[0]),'#FFFFFF')),6)
        with self.assertRaises(ValueError):S.check_palette(['#aabbcc','#AABBCC'])

    def test_strict_no_source_leak(self):
        for bad in ({**S.neutral(),'face_ref':{}},{**S.neutral(),'version':True},
                    {**S.neutral(),'strength':float('nan')},{**S.neutral(),'strength':2},
                    {**S.neutral(),'pattern':'foreign-template'},{**S.neutral(),'colour':'rgb(1,2,3)'}):
            with self.assertRaises(ValueError):S.check(bad)
        for bad in ([True,2,3],[1.2,2,3],[-1,2,3],[256,2,3]):
            with self.assertRaises(ValueError):S.rgb(bad)
        self.assertEqual(S.rgb([255,0,128]),'#FF0080')
        self.assertEqual(set(S.preset(S.neutral())),{'version','pattern','strength','colour'})

    def test_library_rejects_unknown_catalogue_and_corrupt_history(self):
        self.assertEqual(PROJECT.prepare({}),PROJECT.empty())
        with self.assertRaises(ValueError):PROJECT.prepare({PROJECT.KEY:None})
        with self.assertRaises(ValueError):PROJECT.check({**PROJECT.empty(),'catalogue_sha256':'0'*64})
        with self.assertRaises(ValueError):PROJECT.validate_records({'undo':[{PROJECT.KEY:{**PROJECT.empty(),'saved_colours':['#FF0000']*7}}]})
        self.assertEqual(PROJECT.check(PROJECT.empty())['catalogue_sha256'],CATALOGUE_SHA256)

class BlushNative(unittest.TestCase):
    # Requires explicit packaging. Missing .so is a failure, not a skipped/fallback pass.
    def grid(self):
        y,x=np.mgrid[-1:1:80j,-1:1:80j]
        return np.full((80,80,3),.5,np.float32),np.ascontiguousarray(np.stack((x,y),-1),dtype=np.float32),np.ones((80,80),np.float32)

    def test_zero_is_exact_and_support_cannot_leak(self):
        source,uv,support=self.grid()
        self.assertTrue(np.array_equal(delta(source,uv,support,S.neutral()),np.zeros_like(source)))
        support[:,40:]=0
        out=delta(source,uv,support,{**S.neutral(),'strength':1})
        self.assertTrue(np.array_equal(out[:,40:],np.zeros_like(out[:,40:])))
        self.assertGreater(np.count_nonzero(out[:,:40]),0)
        self.assertTrue(np.array_equal(source,np.full_like(source,.5)))

    def test_twelve_spatial_fields_same_colour_and_monotonic_strength(self):
        source,uv,support=self.grid();shapes=set()
        for pattern in S.PATTERNS:
            full=delta(source,uv,support,{**S.neutral(),'pattern':pattern,'strength':1})
            half=delta(source,uv,support,{**S.neutral(),'pattern':pattern,'strength':.5})
            self.assertTrue(np.allclose(full*.5,half,rtol=1e-6,atol=1e-8))
            shapes.add(full.tobytes())
        self.assertEqual(len(shapes),12)

    def test_achromatic_custom_colours_are_not_silent_noops(self):
        source,uv,support=self.grid()
        black=delta(source,uv,support,{**S.neutral(),'strength':1,'colour':'#000000'})
        white=delta(source,uv,support,{**S.neutral(),'strength':1,'colour':'#FFFFFF'})
        self.assertLess(float(black.min()),0);self.assertGreater(float(white.max()),0)

    def test_rgb16_fraction_survives_and_invalid_float_refuses(self):
        source,uv,support=self.grid();source[:]=32769/65535
        out=delta(source,uv,support,{**S.neutral(),'strength':1})
        self.assertTrue(np.isfinite(out).all());self.assertTrue(np.all((source+out>=0)&(source+out<=1)))
        source[0,0,0]=float('nan')
        with self.assertRaises(ValueError):delta(source,uv,support,{**S.neutral(),'strength':1})


class BlushReviewedSupport(unittest.TestCase):
    """Synthetic ownership unit fixture only; NOT real-portrait acceptance."""
    def fixture(self):
        from lumaretouch_engine import people_state as P
        evidence={'backend':'mediapipe','detector_model_sha256':'b'*64,'semantic_model_sha256':'c'*64,
                  'landmark_digest':'d'*64,'status':'verified','source_width':100,'source_height':100,'orientation':'exif_normalized_once'}
        face=P.new_face('a'*64,[.1,.1,.9,.9],evidence)
        state=P.empty();state['faces'][face['face_instance_id']]=face
        def cheek(name,x):return {'visible':True,'unoccluded':True,'ownership_confirmed':True,
            'recipe':{'version':1,'domain':'source-normalized','objects':[{'id':name,'name':name,'enabled':True,'operation':'add',
            'kind':'brush','opacity':1,'feather':20,'points':[[x,.5]],'axes':[[.08,0],[0,.08]]}]}}
        return state,P.face_ref(face),{'left':cheek('left',.3),'right':cheek('right',.7)}

    def test_review_is_bilateral_immutable_and_pinned(self):
        from lumaretouch_engine import blush_makeup_support as V
        from lumaretouch_engine.people_support_assets import check_store
        state,ref,cheeks=self.fixture()
        with self.assertRaises(ValueError):V.retain(state,{},ref,{'left':cheeks['left']})
        candidate,assets=V.retain(state,{},ref,cheeks);check_store(assets)
        self.assertFalse(state['faces'][ref['face_instance_id']]['local_assets'])
        record,key=V.resolve(candidate,assets,ref)
        self.assertEqual(record['face_ref'],ref);self.assertIn(key,assets)
        with self.assertRaises(ValueError):V.resolve(candidate,assets,{**ref,'analysis_revision':1})
        corrupted=json.loads(json.dumps(assets));corrupted[key]['row']['cheeks']['left']['unoccluded']=False
        with self.assertRaises(ValueError):V.resolve(candidate,corrupted,ref)

if __name__=='__main__':unittest.main()
