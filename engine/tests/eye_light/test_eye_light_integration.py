"""UNRUN integration fixtures. Synthetic data tests contracts, not photo quality."""
import unittest
from copy import deepcopy
import numpy as np
from lumaretouch_engine import people_state as P, people_support_assets as A
from lumaretouch_engine import eye_light_support as V, eye_light_state as S
from lumaretouch_engine.eye_light_native import colour
from lumaretouch_engine.people_effects import LocalEffect,apply
from lumaretouch_engine.eye_light_scope import check_params

class EyeLightIntegration(unittest.TestCase):
    def test_registered_stage_preserves_hdr_unaffected_pixels(self):
        src=np.array([[[2.,-.1,.3],[4.,.2,.4]]],np.float32)
        ref={'asset_sha256':'a'*64,'face_instance_id':'face-a','analysis_revision':1}
        row=LocalEffect(ref,'eye_light',(0,0,1,1),delta=np.array([[[.2,.2,.2]]],np.float32))
        out,facts=apply('eye_light',src,[row])
        self.assertGreater(out[0,0,0],2);np.testing.assert_array_equal(out[0,1],src[0,1])
        self.assertEqual(facts['changed_pixels'],1)
    def test_native_transfer_roundtrip_and_neutral_delta(self):
        src=np.array([[[0.,.5,1.],[2.,-.1,.003]]],np.float32)
        self.assertEqual(colour(src).dtype,np.float32)
        np.testing.assert_array_equal(colour(src,np.zeros_like(src)),np.zeros_like(src))
    def test_preset_cannot_smuggle_review(self):
        with self.assertRaises(ValueError):check_params({'recipe':S.neutral(),'support':{}})
    def test_corrupt_visibility_asset_rejected(self):
        with self.assertRaises(ValueError):A.check_store({'a'*64:{'version':1,'face_ref':{},'source':{},'row':{'target':V.KIND}}})
    def test_unreviewed_visibility_rejected(self):
        with self.assertRaises(ValueError):V.check_record({'version':1,'face_ref':{'asset_sha256':'a'*64,'face_instance_id':'face-a','analysis_revision':1},'source':{'sha256':'a'*64,'width':100,'height':100},'row':{'target':V.KIND,'landmark_digest':'b'*64,'eyes':{'left':{'visible':False}}}})
    def test_canonical_registry_has_per_eye_leaves(self):
        from lumaretouch_engine import people_algorithms
        leaves=people_algorithms.defaults()[S.OPERATION]
        self.assertIn('/left/strength',leaves);self.assertIn('/right/rotation',leaves)
        self.assertNotIn('/strength',leaves);self.assertTrue(leaves['/linked'])
