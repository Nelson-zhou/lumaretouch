# SPDX-License-Identifier: GPL-3.0-or-later
"""One immutable source-local contribution, composed by canonical PeopleGraphOwner."""
import numpy as np
from . import lipstick_state as S, people_state as P
from .lipstick_catalogue import CATALOGUE_SHA256
from .lipstick_geometry import geometry
from .lipstick_native import delta as native_delta
from .lip_makeup_runtime import bounds,identity,admit_working_set

class LipstickLayer:
    def __init__(self,window,source,landmarks,excluded,reviewed,*,backend,face_ref,semantic_sha):
        self.window=tuple(window);y,x,h,w=self.window
        if any(type(v) is not int for v in self.window) or min(y,x)<0 or min(h,w)<4 or h*w>32_000_000:raise ValueError('口红源窗口无效或超出预算')
        self.face_ref=P.check_ref(face_ref);P.digest(semantic_sha)
        if type(source) is not np.ndarray or source.dtype!=np.float32 or source.shape!=(h,w,3) or not np.isfinite(source).all() or np.any((source<0)|(source>1)):
            raise ValueError('口红仅支持未量化 working-sRGB float32 修复源；不支持 HDR 场景线性值')
        self.source=np.array(source,copy=True,order='C');self.landmarks=np.array(landmarks,dtype=np.float32,copy=True)-[x,y]
        self.excluded=np.array(excluded,dtype=np.float32,copy=True,order='C');self.reviewed=np.array(reviewed,dtype=np.float32,copy=True,order='C')
        self.backend=backend;self.semantic_sha=semantic_sha;self.key=None;self.delta=None;self.facts={};self.uv=None;self.support=None;self.base=None
        for a in (self.source,self.landmarks,self.excluded,self.reviewed):a.setflags(write=False)
    def solve(self,recipe):
        r=S.check(recipe);key=tuple(r[k] for k in S.KEYS)+(CATALOGUE_SHA256,)
        if key==self.key:return self.delta
        if not S.active(r):self.key=key;self.delta=None;self.facts={'reason':'disabled','changed_pixels':0};return None
        if self.uv is None:
            self.support,self.geometry_facts,self.uv=geometry(self.landmarks,self.source.shape[:2],self.excluded,self.reviewed,backend=self.backend)
            import cv2
            luminance=np.ascontiguousarray(self.source@np.array([.2126,.7152,.0722],np.float32))
            sigma=max(1.,float(np.linalg.norm(self.landmarks[61]-self.landmarks[291]))*.025)
            # Normalized convolution cannot mix teeth/cavity/occluder samples into lip texture.
            den=cv2.GaussianBlur(self.support,(0,0),sigma)
            num=cv2.GaussianBlur(luminance*self.support,(0,0),sigma)
            self.base=np.ascontiguousarray(np.where(den>1e-6,num/np.maximum(den,1e-6),luminance).clip(0,1),dtype=np.float32)
            for a in (self.support,self.uv,self.base):a.setflags(write=False)
        out=native_delta(self.source,self.uv,self.support,self.base,r)
        if not np.isfinite(out).all():raise ValueError('口红产生无效输出，未发布')
        out.setflags(write=False);changed=int(np.count_nonzero(np.any(out!=0,axis=2)))
        self.facts={**self.geometry_facts,'changed_pixels':changed,'reason':None if changed else 'no_measurable_change','recipe':r,
            'face_ref':dict(self.face_ref),'catalogue_sha256':CATALOGUE_SHA256,'semantic_model_sha256':self.semantic_sha,
            'material_limit':'original_approximation_from_existing_lip_texture_not_generated_anatomy'}
        self.key,self.delta=key,out;return out
    def resident_bytes(self):return sum(a.nbytes for a in (self.source,self.landmarks,self.excluded,self.reviewed,self.support,self.uv,self.base,self.delta) if a is not None)

def prepare_record(face_ref,landmarks,recipe,source,*,excluded,backend,semantic_sha,reviewed=None):
    r=S.check(recipe)
    if not S.active(r):return None
    from .people_effects import LocalEffect
    ref=P.check_ref(face_ref);identity(landmarks);P.digest(semantic_sha)
    h,w=source.shape[:2]
    for a in (excluded,reviewed):
        if a is None or a.shape!=(h,w) or not np.isfinite(a).all() or np.any((a<0)|(a>1)):raise ValueError('口红缺少当前源人物的遮挡及可见唇部审核')
    admit_working_set((h,w),landmarks)
    window,lm=bounds(landmarks,h,w);y,x,rh,rw=window
    layer=LipstickLayer(window,source[y:y+rh,x:x+rw],lm,excluded[y:y+rh,x:x+rw],reviewed[y:y+rh,x:x+rw],backend=backend,face_ref=ref,semantic_sha=semantic_sha)
    return LocalEffect(ref,'lipstick',window,delta=layer.solve(r),facts=layer.facts)
