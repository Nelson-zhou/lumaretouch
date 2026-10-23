# SPDX-License-Identifier: GPL-3.0-or-later
"""One reviewed waist inverse subfield; never owns an RGB sampling pass."""
from copy import deepcopy
import numpy as np
from . import waist_shape_state as S,waist_shape_native as N
from . import body_pose_evidence as E,body_pose_manifest as M,body_pose_operations as O


class WaistField:
    operation_id=S.OPERATION_ID

    def __init__(self,row,support_asset,shape,*,source_pixels=None):
        self.record=E.check(row['record']);self.body_ref=self.record['body_ref']
        self.input_binding_sha256=O.field_binding(row,self.operation_id)
        self.shape=tuple(shape);E.whole_source_shape(self.record['source'],self.shape)
        self.recipe=S.check(row['operations'][self.operation_id]['recipe'])
        self.association=deepcopy(row['association']);self.associated_face_id=None
        self.state=None;self.supports=();self.max_displacement=0.
        h,w=self.shape;source=self.record['source']
        self.render_scale=np.array([(w-1)/(source['width']-1),(h-1)/(source['height']-1)],np.float64)
        self.render_scale.setflags(write=False)
        self.facts={'family_id':S.OPERATION_ID,'requirement_id':S.REQUIREMENT_ID,'operation_id':self.operation_id,
                    'body_ref':deepcopy(self.body_ref),'status':'neutral','strategy':'reviewed-visible-contour',
                    'runtime_quality_accepted':False,'ai_segmentation':False,'background_and_garment_transition_may_move':True,
                    'hidden_anatomy_inferred':False,'range_policy':'original-local-inward-0-1'}
        if not S.active(self.recipe):return
        item=row['operations'][self.operation_id];review=item['review'];source=self.record['source']
        if review is None or review['operation_id']!=self.operation_id or review['body_ref']!=self.body_ref or review['points_sha256']!=self.record['points_sha256'] or review['visible_anchors']!=list(S.ANCHORS) or review['support_sha256']!=item['support_sha256'] or review['ownership_confirmed'] is not True:
            raise ValueError('Waist requires its own exact source, pose, bilateral contour and bounds review')
        asset=O.check_support_record(support_asset)
        if E.content_digest(asset)!=item['support_sha256'] or asset['operation_id']!=self.operation_id or asset['kind']!=S.SUPPORT_KIND or asset['body_ref']!=self.body_ref or asset['source']!=source or asset['points_sha256']!=self.record['points_sha256']:
            raise ValueError('Waist support cannot cross source, BodyRef, operation or analysis revision')
        support=S.check_support(asset['data'],self.record)
        if self.record['model_id']!=M.MODEL_ID or self.record['model_sha256']!=M.MODEL_SHA256:
            raise ValueError('Waist orientation model identity changed; explicit reanalysis required')
        # Native geometry stays in exact source pixels. Conjugate the inverse
        # by both decoder scales, including ALIGN=8 aspect rounding.
        start,u,length,scale=S.axis(self.record);h,w=self.shape
        start=np.array(start,np.float64);u=np.array(u,np.float64)
        start+=u*length*support['upper']
        length*=support['lower']-support['upper']
        radius=max(*support['negative'],*support['positive'])*scale*S.FACTOR
        self.state=np.array([*start,*u,length,self.recipe['amount'],S.FACTOR,
                             *(x*scale for x in support['negative']),*(x*scale for x in support['positive'])],np.float64)
        self.state.setflags(write=False);center=(start+u*length*.5)*self.render_scale;center.setflags(write=False)
        self.supports=((center,float(np.hypot(length*.5,radius)*max(self.render_scale))),)
        self.max_displacement=float(.22*self.recipe['amount']*radius*max(self.render_scale))
        self.facts.update(status='prepared-not-rendered',support_sha256=item['support_sha256'],
                          points_sha256=self.record['points_sha256'],pose_model_sha256=self.record['model_sha256'],
                          source_dimensions=[source['width'],source['height']],render_dimensions=[w,h],
                          upper_bound=support['upper'],lower_bound=support['lower'])

    def evaluate(self,points):
        p=np.asarray(points,np.float64)
        if p.ndim!=2 or p.shape[1]!=2 or not np.isfinite(p).all():raise ValueError('Waist field needs finite xy coordinates')
        return np.zeros_like(p) if self.state is None else N.evaluate(self.state,p/self.render_scale)*self.render_scale

    def resident_bytes(self):return self.render_scale.nbytes+(0 if self.state is None else self.state.nbytes)+sum(c.nbytes for c,_ in self.supports)

    def contains(self,points):
        p=np.asarray(points,np.float64)
        if p.ndim!=2 or p.shape[1]!=2 or not np.isfinite(p).all():raise ValueError('Invalid waist support query')
        if self.state is None:return np.zeros(len(p),bool)
        a=self.state[:2];u=self.state[2:4];d=p/self.render_scale-a;t=d@u/self.state[4];v=d@np.array([-u[1],u[0]])
        return (t>0)&(t<1)&(np.abs(v)<max(self.state[7:])*self.state[6])

    def envelope(self):
        s=self.state;a=s[:2];u=s[2:4];n=np.array([-u[1],u[0]]);radius=max(s[7:])*s[6]
        corners=np.array([a+t*s[4]*u+v*radius*n for t in (0,1) for v in (-1,1)])
        corners*=self.render_scale
        return corners.min(axis=0),corners.max(axis=0)
