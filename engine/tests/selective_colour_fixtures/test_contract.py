"""Authored acceptance tests. UNRUN; authorized local tester builds ABI first."""
from copy import deepcopy
import unittest
import numpy as np
from lumaretouch_engine import selective_colour_state as S
from lumaretouch_engine import selective_colour_adapters as A
from lumaretouch_engine.selective_colour_controller import SelectiveColourController
from lumaretouch_engine.selective_colour_stage import SelectiveColourStage

class Host:
    requires_reload = False
    def __init__(self): self.rev=0; self.count=0
    def context(self): return ('doc',self.rev)
    def render_preview(self,recipe,cancelled): return {'seq':11,'slot':1}
    def render_committed(self): return {'seq':12,'slot':0}
    def commit(self,recipe,doc,revision):
        self.count+=1; self.rev+=1
        return {'recipe':recipe,'revision':self.rev,'frame':{'seq':13,'slot':1}}

class Contract(unittest.TestCase):
    def test_strict_and_legacy(self):
        self.assertEqual(S.from_state({}), S.neutral())
        for invalid in [None, {}, {**S.neutral(),'version':True}, {**S.neutral(),'method':'hsl'}]:
            with self.assertRaises(ValueError): S.check(invalid)
        for invalid in [True,float('nan'),float('inf'),101,-101,'1']:
            r=S.neutral();r['ranges']['reds']['cyan']=invalid
            with self.assertRaises(ValueError): S.check(r)
        r=S.neutral();del r['ranges']['blacks']
        with self.assertRaises(ValueError): S.check(r)
    def test_portability_replacement_and_aliases(self):
        r=S.neutral();r['ranges']['reds']['cyan']=20
        preset=A.preset_from_state({S.KEY:r})
        batch=A.prepare_batch([{'other':1},{'other':2}],preset)
        batch[0][S.KEY]['ranges']['reds']['cyan']=99
        self.assertEqual(batch[1][S.KEY],r)
        self.assertEqual(A.apply_preset_to_state(A.apply_preset_to_state({},preset),preset),{S.KEY:r})
        with self.assertRaises(ValueError): A.validate_records({'history':[{S.KEY:r}]},allowed=False)
    def test_neutral_rgb16_exact(self):
        p=np.array([[[0,32768,65535]]],dtype=np.uint16)
        self.assertIs(SelectiveColourStage(S.neutral()).apply_np(p),p)
    def test_relative_absolute_numeric_native(self):
        r=S.neutral();r['ranges']['reds']['cyan']=20
        p=np.array([[[.8,.2,.2]]],dtype=np.float32)
        relative=SelectiveColourStage(r).apply_np(p)
        r['method']='absolute';absolute=SelectiveColourStage(r).apply_np(p)
        np.testing.assert_allclose(relative,[[[.776,.2,.2]]],atol=2e-6)
        np.testing.assert_allclose(absolute,[[[.68,.2,.2]]],atol=2e-6)
    def test_cancel_before_native(self):
        r=S.neutral();r['ranges']['reds']['cyan']=20
        with self.assertRaises(InterruptedError):
            SelectiveColourStage(r).apply_np(np.ones((1,1,3),np.float32),cancelled=lambda:True)
    def test_latest_preview_and_commit_dedup(self):
        h=Host();c=SelectiveColourController(h)
        def message(action,rid,**extra):return {'cmd':'selective_colour','action':action,'request_id':rid,'document_id':'doc','revision':0,**extra}
        c.handle(message('preview','p1',recipe=S.neutral()))
        c.handle(message('preview','p2',recipe=S.neutral()))
        with self.assertRaises(ValueError):c.handle(message('commit','old',preview_id='p1'))
        p=message('commit','apply',preview_id='p2');first=c.handle(p)
        self.assertEqual(c.handle(p),first);self.assertEqual(h.count,1)
        with self.assertRaises(ValueError):c.handle(message('commit','apply',preview_id='p1'))
    def test_invalidate_rejects_pending(self):
        h=Host();c=SelectiveColourController(h)
        p={'cmd':'selective_colour','action':'preview','request_id':'p','document_id':'doc','revision':0,'recipe':S.neutral()}
        c.handle(p);c.invalidate()
        with self.assertRaises(ValueError):c.handle({k:v for k,v in {**p,'action':'commit','request_id':'c','preview_id':'p'}.items() if k!='recipe'})
