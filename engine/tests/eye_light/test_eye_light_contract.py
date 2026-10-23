"""UNRUN: source-authored fixtures. Not acceptance evidence or photo quality proof."""
import unittest
import numpy as np
from lumaretouch_engine import eye_light_state as S
from lumaretouch_engine.eye_light_runtime import export_rgb16_to_linear
class EyeLightContract(unittest.TestCase):
    def test_neutral_and_ranges(self):
        self.assertFalse(S.active(S.neutral()))
        for key in ('horizontal','vertical','rotation'):
            for endpoint in (-100,100):
                r=S.neutral();r['linked']=False;r['left'][key]=endpoint
                self.assertEqual(S.check(r)['left'][key],endpoint)
        for value in (float('nan'),101,-101,True):
            r=S.neutral();r['left']['rotation']=value
            with self.assertRaises(ValueError): S.check(r)
    def test_preset_has_no_face_geometry(self):
        with self.assertRaises(ValueError): S.check(dict(S.neutral(),face_sha256='0'*64))
    def test_rgb16_explicit_decode_preserves_precision(self):
        p=np.array([[[1,32768,65535]]],dtype=np.uint16)
        linear=export_rgb16_to_linear(p,lambda a:a)
        self.assertEqual(linear.dtype,np.float32); self.assertEqual(linear[0,0,0],np.float32(1)/np.float32(65535))
    def test_hdr_and_unmodified_channels_preserved(self):
        from lumaretouch_engine.eye_light_runtime import EyeLightLayer, composite
        from lumaretouch_engine.eye_light_geometry import source_key
        source=np.array([[[2.5,-0.1,0.5],[4.0,0.1,0.2]]],np.float32)
        binding={'source_sha256':source_key(source),'person_id':'person-a','source_revision':3}
        d=np.array([[[0.2,0.2,0.2]]],np.float32)
        layer=EyeLightLayer(S.neutral(),binding,(((0,0,1,1),d),),())
        result=composite(source,layer,person_id='person-a',source_revision=3)
        self.assertGreater(result[0,0,0],1); np.testing.assert_array_equal(result[0,1],source[0,1])
        self.assertEqual(source[0,0,0],np.float32(2.5))
        with self.assertRaises(ValueError): composite(source,layer,person_id='person-b',source_revision=3)
        with self.assertRaises(ValueError): composite(source+np.float32(0.01),layer,person_id='person-a',source_revision=3)

    def test_linked_mismatch_refuses_but_independent_persists(self):
        r=S.neutral();r['left']['strength']=45
        with self.assertRaises(ValueError):S.check(r)
        r['linked']=False;r['right']['rotation']=-25;r['right']['flip']=True
        checked=S.check(r);self.assertEqual(checked['left']['strength'],45);self.assertEqual(checked['right']['rotation'],-25)
    def test_explicit_v1_migration_preserves_selected_side(self):
        old=dict(S.neutral_eye(),version=1,eyes='left',strength=30)
        r=S.check(old);self.assertFalse(r['linked']);self.assertEqual(r['left']['strength'],30);self.assertEqual(r['right']['strength'],0)
