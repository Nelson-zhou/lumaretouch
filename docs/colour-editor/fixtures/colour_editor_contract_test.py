"""UNRUN acceptance scaffolding. Execute only in authorized local validation.
These are not evidence of an executed pass. Native fixtures need packaged ABI1.
"""
import unittest
from lumaretouch_engine import colour_editor_state as S
class RecipeContract(unittest.TestCase):
    def test_neutral(self):
        self.assertFalse(S.active(S.neutral()))
    def test_all_offsets_boundary(self):
        for i in range(3):
            for v in (-100, 100):
                r=S.neutral();r['offsets'][i]=v
                self.assertEqual(S.check(r)['offsets'][i], v)
    def test_nonfinite_rejected(self):
        for v in (float('nan'),float('inf'),True,-101,101):
            r=S.neutral();r['uniformity'][0]=v
            with self.assertRaises(ValueError): S.check(r)
    def test_view_not_serialized(self):
        r=S.neutral();r['show_range']=True
        with self.assertRaises(ValueError): S.check(r)
    def test_unlinked_boundaries(self):
        r=S.neutral();r['linked']=False;r['luminance_smoothness']=.8
        self.assertEqual(S.check(r)['colour_smoothness'],.1)
    def test_link_mismatch_rejected(self):
        r=S.neutral();r['luminance_smoothness']=.8
        with self.assertRaises(ValueError): S.check(r)
