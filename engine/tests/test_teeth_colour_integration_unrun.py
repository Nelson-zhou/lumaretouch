"""AUTHORED / UNRUN: independent controls and source-support plumbing.

Mocked native calls test dispatch/identity only, not native numerical or photo QA.
"""
import unittest
from unittest.mock import patch
import numpy as np
from lumaretouch_engine.ops import enhance as H
from lumaretouch_engine import teeth_colour_apply as T


class TeethIntegrationUnrun(unittest.TestCase):
    def test_independent_keys_do_not_add_support_planes(self):
        self.assertEqual(H.SUBS, ('sclera','iris','teeth'))
        for key in T.KEYS:
            values = H.check_amounts({key:.5})
            self.assertFalse(H.is_identity(values))
            self.assertEqual(H.support_amounts(values), (0,0,.5))
            self.assertEqual(values['teeth'], 0)
            self.assertEqual(values[T.KEYS[1] if key == T.KEYS[0] else T.KEYS[0]], 0)
            for bad in (True, '0.5', float('nan'), -1, 2):
                with self.assertRaises(ValueError): H.check_amounts({key:bad})

    def test_zero_new_values_do_not_call_native(self):
        source = np.full((2,3,3), .4)
        masks = np.zeros((3,2,3), np.float32)
        with patch('lumaretouch_engine.teeth_colour_native.apply') as native:
            out = H.enhance_np(source, masks, {'teeth':.3})
            np.testing.assert_array_equal(source,out)
            native.assert_not_called()

    def test_new_only_dispatches_native_and_preserves_neutral_bits(self):
        source = np.full((3,4,3), .4, np.float64)
        source[1,1,0] = -0.0
        mask = np.zeros((3,4), np.float32)
        mask[1,0] = mask[1,2] = 1
        def correction(rgb, support, brightness, yellow, *, cancelled):
            self.assertEqual((brightness,yellow),(.6,0))
            self.assertEqual(rgb.shape,(1,3,3))
            out = rgb.copy(); out[0,0] += .05
            return out
        with patch('lumaretouch_engine.teeth_colour_native.apply',side_effect=correction):
            out = T.numpy_apply(source,mask,{'teeth_brightness':.6})
        self.assertEqual(out[1,1].tobytes(), source[1,1].tobytes())
        self.assertEqual(out[0].tobytes(), source[0].tobytes())
        self.assertGreater(out[1,0,0],source[1,0,0])
        self.assertEqual(source[1,0,0],.4)

    def test_cancellation_is_forwarded_to_native(self):
        source = np.full((1,2,3), .5,np.float32)
        mask = np.ones((1,2),np.float32)
        stop = lambda: False
        def reject(*args, cancelled):
            self.assertIs(cancelled,stop)
            raise InterruptedError('cancelled')
        with patch('lumaretouch_engine.teeth_colour_native.apply',side_effect=reject):
            with self.assertRaises(InterruptedError):
                T.numpy_apply(source,mask,{'teeth_brightness':1},cancelled=stop)

    def test_strict_cavity_does_not_redefine_photometric_reference_pool(self):
        weight = np.zeros((3,6,6),np.float32); weight[2] = 1
        source = np.full((6,6,3),(.4,.1,.1),np.float32)
        source[2:4,1:5] = (.85,.8,.7)
        cavity = np.zeros((6,6),np.float32); cavity[1:5,1:5] = 1
        info = {'mouth':{},'eyes':[],'strict_teeth':True}
        reg = H.Regions(weight,(0,0,6,6),(6,6),info,teeth_cavity=cavity)
        plain = H.Regions(weight,(0,0,6,6),(6,6),info)
        _, strict_facts = H.refine(reg,source)
        _, old_facts = H.refine(plain,source)
        for key in ('pool_s_mean','pool_v_mean'):
            self.assertEqual(strict_facts['teeth'][key],old_facts['teeth'][key])

    def test_legacy_export_never_silently_skips_active_independent_teeth(self):
        from test_export_per_image_recipe import _batch_snap
        from lumaretouch_engine.export_recipe import build_export_spec
        for key in T.KEYS:
            for deferred in (False,True):
                snap = _batch_snap()
                snap.update(precompute=None, enhance={'amounts':{key:.4}, 'built':False},
                            enhance_defer=deferred)
                with self.assertRaisesRegex(ValueError,'独立牙齿'):
                    build_export_spec(snap,16,20,for_document=True)
