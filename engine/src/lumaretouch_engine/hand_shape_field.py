# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent source-owned hand instance, no body or face landmark fabrication."""
import numpy as np
from . import hand_shape_state as S,hand_shape_native as N
from .optics_candidate_identity import fingerprint


class HandField:
    def __init__(self,recipe,shape):
        self.recipe=S.check(recipe);self.source=self.recipe['source'];self.shape=tuple(shape)
        from .body_pose_evidence import whole_source_shape
        whole_source_shape({**self.source,'orientation':'exif_normalized_once'},self.shape)
        self.instance_id=self.recipe['review']['hand_id'];self.operation_id=S.OP
        self.binding_sha256=fingerprint(self.recipe)
        h,w=self.shape;self.scale=np.array([(self.source['width']-1)/(w-1),(self.source['height']-1)/(h-1)],np.float64)
        states=[];supports=[];prefix=0.
        for region in self.recipe['review']['regions']:
            amount=self.recipe['amounts'][region['kind']]
            if amount==0:continue
            g=S.region_geometry(region,self.source);states.append([*g,.12*amount])
            center=np.array(g[:2],np.float64)/self.scale;center.setflags(write=False)
            supports.append((center,(max(g[4:])+prefix)/float(min(self.scale))))
            prefix+=.12*abs(amount)*g[5]
        self.state=np.frombuffer(np.asarray(states,np.float64).reshape(-1,7).tobytes(),np.float64).reshape(-1,7)
        self.max_source_displacement=min(128.,min(self.source['width'],self.source['height'])*.05)
        self.max_displacement=prefix/float(min(self.scale));self.supports=tuple(supports)
        self.facts={'family':S.FAMILY,'operation_id':S.OP,'hand_id':self.instance_id,'source':self.source,
            'strategy':'manual-visible-support' if self.recipe['proposal'] is None else 'model-proposal-visible-support-reviewed',
            'model_proposal_is_not_visibility':True,'region_count':len(states),'amounts':self.recipe['amounts'],
            'recipe_sha256':self.binding_sha256,'runtime_quality_accepted':False}

    def evaluate(self,points):
        if type(points) is not np.ndarray or points.ndim!=2 or points.shape[1]!=2 or not np.isfinite(points).all():raise ValueError('Hand field requires finite actual off-grid source coordinates')
        if not len(self.state):return np.zeros_like(points)
        return N.evaluate(self.state,points*self.scale,self.source,self.max_source_displacement)/self.scale

    def resident_bytes(self):return self.state.nbytes+self.scale.nbytes+sum(c.nbytes for c,_ in self.supports)


def prepare(recipe,source,shape,*,people_state=None,byte_budget):
    recipe=S.check(recipe)
    if not S.active(recipe):return ()
    if recipe['source']!=S.source(source):raise ValueError('Hand support belongs to a different canonical source')
    field=HandField(recipe,shape)
    if type(byte_budget) is not int or field.resident_bytes()+16*1024*1024>byte_budget:raise ValueError('Hand field preparation exceeds admitted memory budget')
    # Actual retained face boxes can refute ownership; never create a FaceRef for a hand.
    if people_state is not None:
        from .people_state import check
        state=check(people_state);h,w=shape
        for face in state['faces'].values():
            if face['asset_sha256']!=source['sha256']:continue
            x0,y0,x1,y1=face['box'];lo=np.array([x0*(w-1),y0*(h-1)]);hi=np.array([x1*(w-1),y1*(h-1)])
            for center,radius in field.supports:
                if np.linalg.norm(center-np.maximum(lo,np.minimum(hi,center)))<=radius:raise ValueError('Hand transition may reach an observed face; mark smaller separate visible regions')
    return (field,)
