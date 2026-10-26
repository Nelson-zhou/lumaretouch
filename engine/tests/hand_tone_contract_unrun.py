# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored source contract fixtures. UNRUN; no product imports executed here."""
from copy import deepcopy
import unittest
from lumaretouch_engine import hand_tone_state as S, hand_tone_support as M

def stack():
    return {'version':1,'domain':'source-normalized','objects':[]}

class HandToneContract(unittest.TestCase):
    def test_neutral(self):
        self.assertIsNone(S.check(None))
        self.assertFalse(S.active(None))

    def test_bad_radius_and_amount(self):
        for value in (True, 1, 129, 2.5):
            with self.assertRaises(ValueError): S.radius(value)
        for value in (True, -1, 1.01, float('nan')):
            with self.assertRaises(ValueError): S.amount(value)

    def test_no_legacy_clean_donor_contract(self):
        review={'version':1,'domain':'source-normalized','limb':stack(),
                'target':stack(),'protect':stack(),'limb_kind':'hand',
                'same_limb_confirmed':True}
        extra=deepcopy(review);extra['reference']=stack()
        with self.assertRaises(ValueError): M.check_review(extra)
        extra=deepcopy(review);extra['clean_reference_confirmed']=True
        with self.assertRaises(ValueError): M.check_review(extra)
        for kind in ('foot','forearm','face'):
            wrong=deepcopy(review);wrong['limb_kind']=kind
            with self.assertRaises(ValueError): M.check_review(wrong)

    def test_source_budget_and_identity(self):
        for source in ({'sha256':'x','width':10,'height':10},
                       {'sha256':'0'*64,'width':8000,'height':8000},
                       {'sha256':'0'*64,'width':True,'height':10}):
            with self.assertRaises(ValueError): S.source(source)


class HandToneRoiContract(unittest.TestCase):
    def test_real_target_crop_keeps_full_halo_and_origin(self):
        import numpy as np
        from lumaretouch_engine.hand_tone_measure import _target_roi
        target=np.zeros((200,300),np.float32)
        target[80:100,120:150]=1
        self.assertEqual(_target_roi(target,16),(64,104,116,166))
        target[:]=0;target[0:2,0:2]=1
        self.assertEqual(_target_roi(target,16),(0,0,18,18))

    def test_roi_budget_does_not_blanket_exclude_localized_24mp(self):
        from lumaretouch_engine.hand_tone_measure import _needed
        self.assertEqual(_needed(24_000_000,1032*1032),2_330_597_632)
        self.assertLess(_needed(24_000_000,1032*1032),4*1024**3)
        self.assertGreater(_needed(24_000_000,24_000_000),4*1024**3)
        # These are allocation-model fixtures, not executed 24MP image tests.
