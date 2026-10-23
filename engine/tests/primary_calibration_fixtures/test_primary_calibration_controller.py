"""UNRUN protocol fixtures; no product execution authorized in source task."""
import unittest
from lumaretouch_engine.primary_calibration_controller import PrimaryCalibrationController
from lumaretouch_engine.primary_calibration_state import neutral

class Host:
    requires_reload=False
    def __init__(self):self.doc='A';self.rev=1;self.count=0;self.on_render=None
    def context(self):return self.doc,self.rev
    def render_preview(self,recipe,cancelled):
        if self.on_render:self.on_render()
        return {'seq':1,'slot':0}
    def render_committed(self):return {'seq':2,'slot':1}
    def commit(self,recipe,doc,revision):
        self.count+=1;self.rev+=1
        return {'recipe':recipe,'revision':self.rev,'frame':{'seq':3,'slot':0}}

class ProtocolFixtures(unittest.TestCase):
    def setUp(self):self.host=Host();self.c=PrimaryCalibrationController(self.host)
    def msg(self,action,rid,**extra):return {'cmd':'primary_calibration','action':action,'request_id':rid,'document_id':'A','revision':1,**extra}
    def test_commit_idempotence(self):
        self.c.handle(self.msg('preview','p',recipe=neutral()))
        msg=self.msg('commit','c',preview_id='p');a=self.c.handle(msg);b=self.c.handle(msg)
        self.assertEqual(a,b);self.assertEqual(self.host.count,1)
    def test_cancel_removes_pending(self):
        self.c.handle(self.msg('preview','p',recipe=neutral()))
        self.c.handle(self.msg('cancel','x'))
        with self.assertRaises(ValueError):self.c.handle(self.msg('commit','c',preview_id='p'))
    def test_late_document_frame_rejected(self):
        self.host.on_render=lambda:setattr(self.host,'doc','B')
        with self.assertRaises(InterruptedError):self.c.handle(self.msg('preview','p',recipe=neutral()))
    def test_newest_preview_only(self):
        self.c.handle(self.msg('preview','p',recipe=neutral()))
        self.c.handle(self.msg('preview','q',recipe=neutral()))
        with self.assertRaises(ValueError):self.c.handle(self.msg('commit','c',preview_id='p'))
