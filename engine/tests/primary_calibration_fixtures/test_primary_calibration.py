"""UNRUN acceptance fixtures. Execute only in authorized local test environment."""
import unittest
import numpy as np
from lumaretouch_engine import primary_calibration_state as S
from lumaretouch_engine.primary_calibration_native import apply, admit
from lumaretouch_engine.primary_calibration_stage import PrimaryCalibrationStage
from lumaretouch_engine.primary_calibration_adapters import check_preset, prepare_batch

class PrimaryCalibrationFixtures(unittest.TestCase):
    def test_strict_recipe(self):
        for bad in (None, {}, {**S.neutral(), 'version': True}, {**S.neutral(), 'working_space':'display-p3'}):
            with self.assertRaises(ValueError): S.check(bad)
        for v in (True, float('nan'), float('inf'), 101, '1'):
            r=S.neutral();r['red']['hue']=v
            with self.assertRaises(ValueError): S.check(r)
    def test_neutral_identity(self):
        for dtype in (np.uint8,np.uint16,np.float32):
            p=np.array([[[0,1,1]]],dtype=dtype)
            self.assertIs(PrimaryCalibrationStage(S.neutral()).apply_np(p),p)
    def test_gray_and_hdr(self):
        r=S.neutral();r['red']={'hue':10.,'saturation':-10.}
        p=np.array([[[-2.,-2.,-2.],[4.,4.,4.],[0.18,0.18,0.18]]],dtype=np.float32)
        for encoding in ('linear-srgb-d65','extended-srgb-d65'):
            self.assertTrue(np.array_equal(apply(p,r,encoding=encoding),p))
    def test_six_independent_controls(self):
        p=np.array([[[.8,.2,.1],[.2,.8,.1],[.1,.2,.8]]],dtype=np.float32)
        for primary in S.PRIMARIES:
            for field in ('hue','saturation'):
                r=S.neutral();r[primary][field]=-10.
                out=apply(p,r,encoding='linear-srgb-d65')
                self.assertFalse(np.array_equal(out,p))
                self.assertTrue(np.isfinite(out).all())
    def test_rgb16_not_rgb8(self):
        r=S.neutral();r['red']['hue']=1.
        p=np.array([[[12345,23456,34567],[12346,23457,34568]]],dtype=np.uint16)
        out=PrimaryCalibrationStage(r).apply_np(p)
        self.assertEqual(out.dtype,np.uint16)
        self.assertFalse(np.array_equal(out[0,0],out[0,1]))
    def test_invalid_geometry_and_cancel(self):
        r=S.neutral();r['blue']['saturation']=100.
        with self.assertRaises(ValueError):admit(r)
        r=S.neutral();r['red']['hue']=1.
        p=np.ones((1,1,3),dtype=np.float32)
        with self.assertRaises(InterruptedError):apply(p,r,encoding='linear-srgb-d65',cancelled=lambda:True)
        with self.assertRaises(ValueError):apply(p,r,encoding='display-p3')
    def test_replacement_batch(self):
        r=S.neutral();preset={'version':1,'kind':'primary_calibration','recipe':r}
        states=[{'sentinel':1},{'sentinel':2}];out=prepare_batch(states,preset)
        self.assertNotIn(S.KEY,states[0]);out[0][S.KEY]['red']['hue']=5
        self.assertEqual(out[1][S.KEY]['red']['hue'],0)
        with self.assertRaises(ValueError):check_preset({**preset,'version':True})
