# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual off-grid leg length subfield, consumed by the shared per-BodyRef geometry."""
from copy import deepcopy
import numpy as np
from . import body_pose_evidence as E, body_pose_manifest as M, body_pose_operations as O
from . import leg_length_state as S, leg_length_native as N


class LegLengthField:
    operation_id = S.OPERATION_ID

    def __init__(self, row, support_asset, shape):
        self.record = E.check(row['record']); self.body_ref = self.record['body_ref']
        item = row['operations'][self.operation_id]
        self.input_binding_sha256 = O.field_binding(row, self.operation_id)
        self.recipe = S.check(item['recipe']); self.shape = tuple(shape)
        self.association = deepcopy(row['association']); self.associated_face_id = None
        self.state = None; self.supports = (); self.max_displacement = 0.
        if len(self.shape) != 2: raise ValueError('Leg length field needs an image shape')
        h,w = self.shape; source = self.record['source']
        E.whole_source_shape(source,self.shape)
        self.facts = {'operation_id':self.operation_id,'body_ref':deepcopy(self.body_ref),
                      'status':'neutral','model_sha256':self.record['model_sha256'],
                      'points_sha256':self.record['points_sha256'],
                      'source_dimensions':[source['width'],source['height']],
                      'render_dimensions':[w,h], 'background_may_move':True,
                      'runtime_quality_accepted':False}
        if not S.active(self.recipe): return
        review = item['review']
        if review is None or review['operation_id'] != self.operation_id or review['body_ref'] != self.body_ref or review['points_sha256'] != self.record['points_sha256'] or review['visible_anchors'] != list(S.REQUIRED_ANCHORS) or review['ownership_confirmed'] is not True or review['support_sha256'] != item['support_sha256']:
            raise ValueError('Leg-specific visible hip/knee/ankle and contour review is required; shoulder review is not authorization')
        asset = O.check_support_record(support_asset)
        if E.content_digest(asset) != item['support_sha256'] or asset['operation_id'] != self.operation_id or asset['kind'] != S.SUPPORT_KIND or asset['body_ref'] != self.body_ref or asset['source'] != source or asset['points_sha256'] != self.record['points_sha256']:
            raise ValueError('Leg length support does not belong to this exact source and actual full pose observation')
        support = S.policy_check_support(asset['data'], self.record)
        if self.record['model_id'] != M.MODEL_ID or self.record['model_sha256'] != M.MODEL_SHA256:
            raise ValueError('Leg length observations came from different model bytes; explicitly reanalyse')
        points = np.array([[p[k] for k in ('x','y','z','visibility','presence')] for p in self.record['points']], np.float64)
        self.state = N.prepare(points, S.vector(self.recipe), S.support_vector(support), self.shape)
        disks = []
        bounds = []
        for start in (0,13):
            s = self.state[start:start+13]
            c = np.array([(s[0]+s[3])/2,(s[4]+s[8])/2]); c.setflags(write=False)
            disks.append((c,float(np.hypot((s[3]-s[0])/2,(s[8]-s[4])/2))))
            bounds.append(max(float(np.linalg.norm(s[9:11])),float(np.linalg.norm(s[9:11]+s[11:13]))))
        self.supports = tuple(disks)
        self.max_displacement = sum(bounds)
        self.facts.update(status='prepared-not-rendered',backend=E.BACKEND,
                          requested_recipe=deepcopy(self.recipe),support_sha256=item['support_sha256'],
                          support_policy=S.SUPPORT_KIND, segment_order=list(S.SIDES),
                          fixed_joint_indices=[23,24], moving_joint_indices=[25,26,27,28,29,30,31,32])

    def evaluate(self, points):
        p = np.asarray(points,np.float64)
        if p.ndim != 2 or p.shape[1] != 2 or not np.isfinite(p).all():
            raise ValueError('Leg length evaluation needs finite xy coordinates')
        return np.zeros_like(p) if self.state is None else N.evaluate(self.state,p)

    def resident_bytes(self):
        return (0 if self.state is None else self.state.nbytes) + sum(c.nbytes for c,_ in self.supports)

    def contains(self, points):
        p = np.asarray(points,np.float64)
        if p.ndim != 2 or p.shape[1] != 2 or not np.isfinite(p).all():
            raise ValueError('Leg length support query needs finite xy coordinates')
        result = np.zeros(len(p),bool)
        if self.state is not None:
            for start in (0,13):
                s = self.state[start:start+13]
                result |= (p[:,0]>s[0])&(p[:,0]<s[3])&(p[:,1]>s[4])&(p[:,1]<s[8])
        return result
