# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual off-grid leg subfield, consumed by the shared per-BodyRef geometry."""
from copy import deepcopy
import numpy as np
from . import body_pose_evidence as E, body_pose_manifest as M, body_pose_operations as O
from . import leg_shape_state as S, leg_shape_native as N


class LegField:
    operation_id = S.OPERATION_ID

    def __init__(self, row, support_asset, shape):
        self.record = E.check(row['record']); self.body_ref = self.record['body_ref']
        item = row['operations'][self.operation_id]
        self.input_binding_sha256 = O.field_binding(row, self.operation_id)
        self.recipe = S.check(item['recipe']); self.shape = tuple(shape)
        self.association = deepcopy(row['association']); self.associated_face_id = None
        self.state = None; self.supports = (); self.max_displacement = 0.
        if len(self.shape) != 2: raise ValueError('Leg field needs an image shape')
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
            raise ValueError('Leg support does not belong to this exact source and actual full pose observation')
        support = S.policy_check_support(asset['data'], self.record)
        if self.record['model_id'] != M.MODEL_ID or self.record['model_sha256'] != M.MODEL_SHA256:
            raise ValueError('Leg observations came from different model bytes; explicitly reanalyse')
        points = np.array([[p[k] for k in ('x','y','z','visibility','presence')] for p in self.record['points']], np.float64)
        self.state = N.prepare(points, S.vector(self.recipe), S.support_vector(support), self.shape)
        disks = []
        for start in range(0,28,7):
            a = self.state[start:start+2]; axis = self.state[start+2:start+4]
            length, radius, amount = self.state[start+4:start+7]
            if amount == 0: continue
            c = np.array(a+axis*length*.5); c.setflags(write=False)
            disks.append((c,float(np.hypot(length*.5,radius))))
        self.supports = tuple(disks)
        self.max_displacement = float(sum(.25*abs(self.state[i+6])*self.state[i+5] for i in range(0,28,7)))
        self.facts.update(status='prepared-not-rendered',backend=E.BACKEND,
                          requested_recipe=deepcopy(self.recipe),support_sha256=item['support_sha256'],
                          support_policy=S.SUPPORT_KIND, segment_order=list(S.SEGMENTS),
                          fixed_joint_indices=list(S.REQUIRED_ANCHORS))

    def evaluate(self, points):
        p = np.asarray(points,np.float64)
        if p.ndim != 2 or p.shape[1] != 2 or not np.isfinite(p).all():
            raise ValueError('Leg evaluation needs finite xy coordinates')
        return np.zeros_like(p) if self.state is None else N.evaluate(self.state,p)

    def resident_bytes(self):
        return (0 if self.state is None else self.state.nbytes) + sum(c.nbytes for c,_ in self.supports)

    def contains(self, points):
        p = np.asarray(points,np.float64)
        if p.ndim != 2 or p.shape[1] != 2 or not np.isfinite(p).all():
            raise ValueError('Leg support query needs finite xy coordinates')
        result = np.zeros(len(p),bool)
        if self.state is not None:
            for start in range(0,28,7):
                a = self.state[start:start+2]; axis = self.state[start+2:start+4]
                length,radius,amount = self.state[start+4:start+7]
                if amount == 0: continue
                relative = p-a; t = relative@axis/length
                transverse = relative@np.array([-axis[1],axis[0]])
                result |= (t>0)&(t<1)&(np.abs(transverse)<radius)
        return result
