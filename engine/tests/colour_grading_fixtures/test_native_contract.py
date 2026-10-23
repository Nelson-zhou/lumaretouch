"""UNRUN; requires prebuilt Rust core. No numerical fallback permitted."""
import unittest
import numpy as np
from lumaretouch_engine import colour_grading_state as S
from lumaretouch_engine.colour_grading_stage import ColourGradingStage


class ColourGradingNative(unittest.TestCase):
    def test_rgb16_neutral_identity(self):
        rgb = np.arange(3 * 127, dtype=np.uint16).reshape(1, 127, 3)
        self.assertIs(ColourGradingStage(S.neutral()).apply_np(rgb), rgb)

    def test_hdr_and_shadow_mid_highlight_masks(self):
        p = np.array([[[0.01]*3,[0.18]*3,[4.0]*3]], dtype=np.float32)
        for key, index in [('shadows',0),('midtones',1),('highlights',2)]:
            r = S.neutral(); r[key]['saturation']=50; r[key]['hue']=240
            q = ColourGradingStage(r).apply_np(p, encoding='linear-srgb-d65')
            self.assertTrue(np.isfinite(q).all())
            self.assertGreater(q[0,index,2], q[0,index,0])
        self.assertGreater(q.max(),1)

    def test_rgb16_no_eight_bit_quantization(self):
        r=S.neutral();r['global']['luminance']=1
        p=np.repeat(np.arange(20000,21000,dtype=np.uint16)[:,None],3,axis=1)[None,:,:]
        q=ColourGradingStage(r).apply_np(p)
        self.assertEqual(q.dtype,np.uint16)
        self.assertGreater(len(np.unique(q)),500)

    def test_cancel_and_no_partial_mutation(self):
        r=S.neutral();r['global']['saturation']=30
        p=np.full((300,300,3),0.18,np.float32); before=p.copy();calls=[0]
        def cancel(): calls[0]+=1;return calls[0]>3
        with self.assertRaises(InterruptedError): ColourGradingStage(r).apply_np(p,cancelled=cancel)
        np.testing.assert_array_equal(p,before)
