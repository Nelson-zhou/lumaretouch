"""Compact inverse body field with people_geometry-compatible evaluator contract."""
import numpy as np
from . import body_pose_evidence as E, body_pose_manifest as M, shoulder_shape_state as S
from . import shoulder_shape_native as N,body_pose_operations as O


class ShoulderField:
    def __init__(self,row,shape):
        self.record=E.check(row['record']);self.body_ref=self.record['body_ref'];self.operation_id=S.OPERATION_ID;item=row['operations'][self.operation_id];self.recipe=S.check(item['recipe'])
        self.input_binding_sha256=O.field_binding(row,self.operation_id)
        self.shape=tuple(shape);self.state=None;self.association=row['association'];self.supports=();self.max_displacement=0.
        h,w=self.shape;source=self.record['source']
        E.whole_source_shape(source,(h,w))
        self.facts={'input_binding_sha256':self.input_binding_sha256,'operation_id':S.OPERATION_ID,'body_ref':self.body_ref,'status':'neutral','model_sha256':self.record['model_sha256'],'points_sha256':self.record['points_sha256'],'source_dimensions':[source['width'],source['height']],'render_dimensions':[w,h],'background_may_move':True,'runtime_quality_accepted':False}
        if not S.active(self.recipe):return  # Exact identity, no model/native allocation.
        review=item['review']
        if review is None or review['operation_id']!=self.operation_id or review['support_sha256'] is not None or review['body_ref']!=self.body_ref or review['points_sha256']!=self.record['points_sha256'] or review['visible_anchors']!=list(E.ANCHORS) or review['ownership_confirmed'] is not True:raise ValueError('Review visible head, shoulders, elbows, torso and body ownership before shaping')
        if self.record['model_id']!=M.MODEL_ID or self.record['model_sha256']!=M.MODEL_SHA256:raise ValueError('Retained body observations came from different model bytes; reanalyse explicitly')
        points=np.array([[p[k] for k in ('x','y','z','visibility','presence')] for p in self.record['points']],np.float64)
        self.state=N.prepare(points,S.vector(self.recipe),self.shape)
        self.supports=tuple((self.state[i:i+2].copy(),float(self.state[i+2])) for i in (0,5))
        for c,_r in self.supports:c.setflags(write=False)
        self.max_displacement=float(max(np.linalg.norm(self.state[3:5]),np.linalg.norm(self.state[8:10])))
        self.facts.update(status='prepared-not-rendered',backend=E.BACKEND,requested_recipe=self.recipe,
                          support_policy='compact-visible-shoulder-disks-fixed-head-elbow-hip-outside',
                          max_requested_shift=float(max(np.linalg.norm(self.state[3:5]),np.linalg.norm(self.state[8:10]))))

    def evaluate(self,points):
        p=np.asarray(points,np.float64)
        if p.ndim!=2 or p.shape[1]!=2 or not np.isfinite(p).all():raise ValueError('Shoulder evaluation requires finite xy coordinates')
        return np.zeros_like(p) if self.state is None else N.evaluate(self.state,p)

    def resident_bytes(self):
        return (0 if self.state is None else self.state.nbytes)+sum(c.nbytes for c,_ in self.supports)

    def contains(self,points):
        p=np.asarray(points,np.float64);result=np.zeros(len(p),bool)
        for center,radius in self.supports:result|=np.linalg.norm(p-center,axis=1)<radius
        return result
