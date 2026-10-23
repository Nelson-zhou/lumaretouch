# SPDX-License-Identifier: GPL-3.0-or-later
"""Frozen float contribution, using the established lip ROI and people compositor.

One solve per real source face and recipe; full-resolution export crops the same
field using people_pipeline._local. No RGB8 conversion, in-place repair mutation,
per-tile solve, second history owner, or source/person reassignment.
"""
import numpy as np
from . import blush_makeup_state as S, people_state as P
from .blush_makeup_catalogue import CATALOGUE_SHA256
from .blush_makeup_geometry import fields
from .blush_makeup_native import delta as native_delta
from .lip_makeup_runtime import bounds, identity

class BlushMakeupLayer:
    def __init__(self,window,source,landmarks,skin,excluded,*,backend,face_ref,semantic_sha):
        self.window=tuple(window);y,x,h,w=self.window
        if len(self.window)!=4 or any(type(v) is not int for v in self.window) or min(y,x)<0 or min(h,w)<4 or h*w>32_000_000:
            raise ValueError('腮红全尺寸源窗口无效或超出预算')
        self.face_ref=P.check_ref(face_ref);P.digest(semantic_sha)
        if type(source) is not np.ndarray or source.dtype!=np.float32 or source.shape!=(h,w,3) or not np.isfinite(source).all() or np.any((source<0)|(source>1)):
            raise ValueError('腮红需要未量化 working-sRGB float32 修复源；不接受 HDR 场景线性值偷裁切')
        self.source=np.array(source,copy=True,order='C')
        self.landmarks=np.array(landmarks,dtype=np.float32,copy=True)-[x,y]
        self.skin=None if skin is None else np.array(skin,dtype=np.float32,copy=True,order='C')
        self.excluded=None if excluded is None else np.array(excluded,dtype=np.float32,copy=True,order='C')
        self.backend=backend;self.semantic_sha=semantic_sha;self.key=None;self.delta=None;self.facts={}
        self.uv=None;self.support=None;self.cheek_owner=None
        for array in (self.source,self.landmarks,self.skin,self.excluded):
            if array is not None:array.setflags(write=False)

    def solve(self,recipe):
        r=S.check(recipe);key=(r['pattern'],r['strength'],r['colour'],CATALOGUE_SHA256)
        if self.key==key:return self.delta
        if not S.active(r):
            self.key=key;self.delta=None;self.facts={'reason':'disabled','changed_pixels':0}
            return None
        if self.uv is None:
            self.uv,self.support,self.cheek_owner,self.geometry_facts=fields(self.landmarks,self.source.shape[:2],self.skin,self.excluded,backend=self.backend)
            self.uv.setflags(write=False);self.support.setflags(write=False);self.cheek_owner.setflags(write=False)
        result=native_delta(self.source,self.uv,self.support,r)
        if not np.isfinite(result).all():raise ValueError('腮红输出非有限数值；未发布')
        result.setflags(write=False)
        changed_mask=np.any(result!=0,axis=2)
        changed=int(np.count_nonzero(changed_mask))
        per_cheek=[int(np.count_nonzero(changed_mask&(self.cheek_owner==side))) for side in (1,2)]
        if changed and min(per_cheek)<8:raise ValueError('所选图案一侧有效支持不足；未部分应用腮红')
        self.facts={**self.geometry_facts,'face_ref':dict(self.face_ref),'catalogue_sha256':CATALOGUE_SHA256,
                    'semantic_model_sha256':self.semantic_sha,'changed_pixels':changed,'changed_per_cheek':per_cheek,
                    'reason':None if changed else 'no_measurable_change','recipe':r}
        self.key,self.delta=key,result
        return self.delta

    def resident_bytes(self):
        return sum(a.nbytes for a in (self.source,self.landmarks,self.skin,self.excluded,self.uv,self.support,self.cheek_owner,self.delta) if a is not None)


def prepare_record(face_ref,landmarks,recipe,source,*,excluded,skin,backend,semantic_sha,reviewed=None):
    """Call after people_render_runtime.verify_analysis, before atomic publish."""
    r=S.check(recipe)
    if not S.active(r):return None # Exact neutral, no semantic/native availability dependency.
    from .people_effects import LocalEffect
    ref=P.check_ref(face_ref);identity(landmarks);P.digest(semantic_sha)
    if skin is None or excluded is None:raise ValueError('腮红缺少真实皮肤及遮挡支持')
    h,w=source.shape[:2]
    if reviewed is None or reviewed.shape!=(h,w) or not np.isfinite(reviewed).all() or np.any((reviewed<0)|(reviewed>1)):raise ValueError('请先审核此人物两侧可见面颊皮肤')
    skin=np.ascontiguousarray(skin*reviewed,dtype=np.float32)
    if skin.shape!=(h,w) or excluded.shape!=(h,w):raise ValueError('腮红皮肤及遮挡场与源图不一致')
    window,lm=bounds(landmarks,h,w);y,x,rh,rw=window
    layer=BlushMakeupLayer(window,source[y:y+rh,x:x+rw],lm,skin[y:y+rh,x:x+rw],excluded[y:y+rh,x:x+rw],
        backend=backend,face_ref=ref,semantic_sha=semantic_sha)
    result=layer.solve(r)
    return LocalEffect(ref,'blush_makeup',window,delta=result,facts=layer.facts)
