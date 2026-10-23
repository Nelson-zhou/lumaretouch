# SPDX-License-Identifier: GPL-3.0-or-later
"""One actual segment subfield for the shared same-BodyRef off-grid chain."""
from copy import deepcopy
import numpy as np
from . import arm_shape_state as S, arm_shape_native as N
from . import body_pose_evidence as E, body_pose_manifest as M, body_pose_operations as O


class ArmField:
    def __init__(self,row,support_asset,shape,operation_id,*,source_pixels=None):
        self.operation_id=operation_id;self.segment=S.segment_for(operation_id)
        self.record=E.check(row['record']);self.body_ref=self.record['body_ref']
        self.input_binding_sha256=O.field_binding(row,operation_id)
        self.shape=tuple(shape);E.whole_source_shape(self.record['source'],self.shape)
        self.recipe=S.check(row['operations'][operation_id]['recipe'])
        self.association=deepcopy(row['association']);self.associated_face_id=None
        self.state=None;self.supports=();self.max_displacement=0.
        self.facts={'family_id':S.FAMILY_ID,'requirement_id':S.REQUIREMENT_ID,'operation_id':operation_id,
                    'body_ref':deepcopy(self.body_ref),'segment':self.segment,'status':'neutral',
                    'runtime_quality_accepted':False,'background_and_garment_transition_may_move':True}
        if not S.active(self.recipe): return
        item=row['operations'][operation_id];review=item['review'];source=self.record['source']
        if review is None or review['operation_id']!=operation_id or review['body_ref']!=self.body_ref or review['points_sha256']!=self.record['points_sha256'] or review['visible_anchors']!=list(S.JOINTS[self.segment]) or review['support_sha256']!=item['support_sha256'] or review['ownership_confirmed'] is not True:
            raise ValueError('This arm side/segment requires its own exact source/pose/contour review')
        asset=O.check_support_record(support_asset)
        if E.content_digest(asset)!=item['support_sha256'] or asset['operation_id']!=operation_id or asset['kind']!=S.SUPPORT_KIND or asset['body_ref']!=self.body_ref or asset['source']!=source or asset['points_sha256']!=self.record['points_sha256']:
            raise ValueError('Arm support cannot cross source, BodyRef, operation or analysis revision')
        support=S.check_support(asset['data'],self.record,segment=self.segment)
        if support['strategy']!=self.recipe['strategy']:
            raise ValueError('Requested arm strategy lacks matching reviewed evidence; no AI/manual fallback')
        if self.record['model_id']!=M.MODEL_ID or self.record['model_sha256']!=M.MODEL_SHA256:
            raise ValueError('Arm pose model identity changed; explicit reanalysis is needed')
        if support['selection'] is not None:
            if type(source_pixels) is not dict:
                if not isinstance(source_pixels,np.ndarray): raise ValueError('Neural contour replay needs verified full-source inference pixels')
                if source_pixels.shape!=(source['height'],source['width'],3): raise ValueError('Neural support cannot be verified with a preview/proxy input')
            # Dict is only the canonical-source-bound immutable model packet;
            # verify_input rejects arbitrary proxies, stale source and bytes.
            from .arm_shape_selection import verify_input
            verify_input(source_pixels,support['selection'])
        h,w=self.shape;a,b=(self.record['points'][i] for i in S.JOINTS[self.segment])
        start=np.array([a['x']*(w-1),a['y']*(h-1)],np.float64)
        d=np.array([(b['x']-a['x'])*(w-1),(b['y']-a['y'])*(h-1)],np.float64)
        length=float(np.linalg.norm(d));u=d/length;scale=min(w-1,h-1)
        factor=S.FACTORS[self.recipe['strategy']];radius=max(*support['negative'],*support['positive'])*scale*factor
        self.state=np.array([*start,*u,length,self.recipe['amount'],factor,
                             *(x*scale for x in support['negative']),*(x*scale for x in support['positive'])],np.float64)
        self.state.setflags(write=False)
        center=start+u*length*.5;center.setflags(write=False)
        self.supports=((center,float(np.hypot(length*.5,radius))),)
        self.max_displacement=float(.22*self.recipe['amount']*radius)
        self.facts.update(status='prepared-not-rendered',strategy=self.recipe['strategy'],
                          support_sha256=item['support_sha256'],points_sha256=self.record['points_sha256'],
                          pose_model_sha256=self.record['model_sha256'],source_dimensions=[source['width'],source['height']],
                          render_dimensions=[w,h],selection_receipt=None if support['selection'] is None else {
                          k:deepcopy(support['selection'][k]) for k in ('binding','runtime_sha256','actual_device')})

    def evaluate(self,points):
        p=np.asarray(points,np.float64)
        if p.ndim!=2 or p.shape[1]!=2 or not np.isfinite(p).all(): raise ValueError('Arm field needs finite xy coordinates')
        return np.zeros_like(p) if self.state is None else N.evaluate(self.state,p)

    def resident_bytes(self):
        return (0 if self.state is None else self.state.nbytes)+sum(c.nbytes for c,_ in self.supports)

    def contains(self,points):
        p=np.asarray(points,np.float64)
        if p.ndim!=2 or p.shape[1]!=2 or not np.isfinite(p).all(): raise ValueError('Invalid arm support query')
        if self.state is None: return np.zeros(len(p),bool)
        a=self.state[:2];u=self.state[2:4];length=self.state[4];radius=max(self.state[7:])*self.state[6]
        d=p-a;t=d@u/length;v=d@np.array([-u[1],u[0]])
        return (t>0)&(t<1)&(np.abs(v)<radius)  # conservative, never understates support
