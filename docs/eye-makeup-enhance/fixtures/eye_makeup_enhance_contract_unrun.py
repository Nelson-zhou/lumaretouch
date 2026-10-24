# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Requires normal authorized test environment, not imported here."""
import copy
import unittest
from lumaretouch_engine import eye_makeup_enhance_state as S
from lumaretouch_engine import eye_makeup_enhance_support as V
from lumaretouch_engine import eye_makeup_enhance_project as J

class RecipeContracts(unittest.TestCase):
    def test_neutral_and_independent_modes(self):
        r=S.neutral(); self.assertFalse(S.active(r))
        r['amount']={'linked':False,'left':-.5,'right':.3}
        r['saturation']={'linked':True,'left':.2,'right':.2}
        self.assertEqual(S.check(r),r)
        self.assertTrue(S.side_active(r,'left'))
        self.assertEqual(S.side_controls(r,'right')['amount'],.3)
    def test_reject_bools_nonfinite_unknown_and_link_mismatch(self):
        for value in (True,float('nan'),float('inf'),1.01,-1.01,10**500):
            r=S.neutral();r['brightness']['linked']=False;r['brightness']['left']=value
            with self.assertRaises(ValueError):S.check(r)
        r=S.neutral();r['structure']['right']=.2
        with self.assertRaises(ValueError):S.check(r)
        r=S.neutral();r['source']='donor'
        with self.assertRaises(ValueError):S.check(r)
    def test_leaves_do_not_accept_support_or_palette(self):
        for path in ('/left','/amount','/amount/colour','/makeup','/reference_a'):
            with self.assertRaises(ValueError):J.validate_leaf(path,0)
        with self.assertRaises(ValueError):J.validate_leaf('/amount/linked',1)
        J.validate_leaf('/structure/right',-.4)

class ReviewSchemaContracts(unittest.TestCase):
    def eye(self):
        # Synthetic schema coordinates are NOT verified face evidence or a photo.
        return {'makeup':[[.2,.2],[.3,.2],[.3,.3],[.2,.3]],'exclusions':[],
            'reference_a':None,'reference_b':None,'reference_confirmed':False,
            'visible_makeup':True,'unoccluded':True,'ownership_confirmed':True,'globe_lashes_brows_excluded':True}
    def test_optional_reference_keeps_subcontrols_possible(self):
        self.assertEqual(V.check_eyes({'left':self.eye()}),{'left':self.eye()})
    def test_no_borrowed_consent_or_one_reference(self):
        eye=self.eye();eye['visible_makeup']=False
        with self.assertRaises(ValueError):V.check_eyes({'left':eye})
        eye=self.eye();eye['reference_a']=[[.4,.4],[.5,.4],[.5,.5]]
        with self.assertRaises(ValueError):V.check_eyes({'left':eye})
    def test_self_intersection_and_duplicate_rejected(self):
        for points in ([[.1,.1],[.9,.9],[.1,.9],[.9,.1]],[[.1,.1],[.9,.1],[.9,.9],[.1,.1]]):
            with self.assertRaises(ValueError):V.polygon(points)
    def test_record_rejects_stale_source_and_foreign_kind(self):
        ref={'asset_sha256':'a'*64,'face_instance_id':'synthetic-fixture','analysis_revision':1}
        record={'version':1,'face_ref':ref,'source':{'sha256':'a'*64,'width':100,'height':100},
            'row':{'target':V.KIND,'landmark_digest':'b'*64,'eyes':{'left':self.eye()}}}
        V.check_record(record)
        altered=copy.deepcopy(record);altered['source']['sha256']='c'*64
        with self.assertRaises(ValueError):V.check_record(altered)
        record['row']['target']='iris_makeup_visibility'
        with self.assertRaises(ValueError):V.check_record(record)
