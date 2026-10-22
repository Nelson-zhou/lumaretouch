"""One frozen repaired-source face ROI; cache a bounded additive RGB field.

All controls solve together. Export constructs one original-resolution layer,
then slices it for every RGB8/RGB16 tile. Never solve on a tile or previous
corrected pixels. Recovery consumes only this operator's before/after pair.
"""
import numpy as np
from . import lip_makeup_state as S
from .lip_makeup_geometry import geometry
from .lip_makeup_native import propose


class LipMakeupLayer:
    def __init__(self, window, pixels, landmarks_px, excluded, *, backend, identity):
        self.window = tuple(window)
        y,x,h,w = self.window
        if any(type(v) is not int for v in self.window) or min(y,x)<0 or min(h,w)<4 or h*w>32_000_000:
            raise ValueError('唇妆全尺寸源窗口无效或超出预算')
        source = np.asarray(pixels,np.float32)
        if source.shape != (h,w,3) or not np.isfinite(source).all() or np.any((source<0)|(source>1)):
            raise ValueError('唇妆需要未量化 working-sRGB float32 修复源')
        self.source = np.array(source,dtype=np.float32,order='C',copy=True)
        self.landmarks = np.array(landmarks_px,dtype=np.float32,copy=True)
        self.excluded = None if excluded is None else np.array(excluded,dtype=np.float32,order='C',copy=True)
        self.backend, self.identity = backend, str(identity)
        self.source_version = None
        self.key = None; self.delta = None; self.facts = {}
        self.mask = None; self.lab = None; self.shading = None
        for a in (self.source,self.landmarks,self.excluded):
            if a is not None: a.setflags(write=False)

    def _prepare(self):
        if self.mask is not None: return
        import cv2
        y,x,h,w = self.window
        self.mask,self.geometry_fact,width = geometry(self.landmarks-[x,y],(h,w),self.source,
                                                      self.excluded,backend=self.backend)
        if self.geometry_fact['reason']: return
        self.lab = cv2.cvtColor(self.source,cv2.COLOR_RGB2Lab)
        # Normalized low-pass sees ONLY measured eligible lips, never teeth or
        # nearby skin. Difference from the lip-weighted mean is existing broad
        # and middle-scale modelling. Pores/high-frequency L are not amplified.
        sigma = max(1.2,width*.035)
        denominator = cv2.GaussianBlur(self.mask,(0,0),sigma,borderType=cv2.BORDER_REFLECT_101)
        numerator = cv2.GaussianBlur(self.lab[...,0]*self.mask,(0,0),sigma,borderType=cv2.BORDER_REFLECT_101)
        mean = float(np.sum(self.lab[...,0]*self.mask,dtype=np.float64)/np.sum(self.mask,dtype=np.float64))
        low = np.divide(numerator,denominator,out=np.full_like(numerator,mean),where=denominator>1e-6)
        self.shading = np.ascontiguousarray(np.clip(low-mean,-20,20),dtype=np.float32)

    def solve(self, recipe):
        r = S.check(recipe); key = tuple(r[k] for k in S.KEYS)
        if key == self.key: return self.delta
        if not any(key):
            self.delta=None; self.key=key
            self.facts={'reason':'disabled','gated_px':0,'changed_px':0,'face_identity':self.identity}
            return None  # Exact identity; no conversion, inference or native load.
        self._prepare()
        facts={**self.geometry_fact,'face_identity':self.identity,'changed_px':0}
        if facts['reason']:
            # Requested active unsupported effect is an actionable rejection,
            # not a successful edit receipt with unchanged output.
            self.facts=facts
            raise ValueError('唇妆未应用：'+facts['reason'])
        import cv2
        corrected=cv2.cvtColor(propose(self.lab,self.shading,r),cv2.COLOR_Lab2RGB)
        # Simultaneous bounded contribution, NOT replacement with source-based
        # corrected pixels. Earlier operators' unrelated changes are retained.
        delta=np.ascontiguousarray(np.where(self.mask[...,None]>0,
            np.clip(corrected-self.source,-.18,.18)*self.mask[...,None],0),dtype=np.float32)
        if not np.isfinite(delta).all(): raise ValueError('唇妆产生无效像素，未更新缓存')
        facts['changed_px']=int(np.count_nonzero(np.max(np.abs(delta),axis=2)>1e-7))
        facts['controls']={k:r[k] for k in S.KEYS}
        if not facts['changed_px']: facts['reason']='no_measurable_change'
        self.delta,self.key,self.facts=delta,key,facts
        return delta

    def resident_bytes(self):
        return sum(a.nbytes for a in (self.source,self.landmarks,self.excluded,self.mask,self.lab,self.shading,self.delta) if a is not None)


def attach_delta(pipe,window,delta,origin=(0,0)):
    """Crop the already solved full-source field, including edge-crossing tiles."""
    pipe.lip_makeup_delta=None; pipe.lip_makeup_local=None
    if delta is None: return
    import torch
    y,x,h,w=window
    if delta.shape!=(h,w,3) or not np.isfinite(delta).all(): raise ValueError('唇妆导出场无效')
    y-=origin[0]; x-=origin[1]
    y0,x0=max(0,y),max(0,x); y1,x1=min(pipe.h,y+h),min(pipe.w,x+w)
    if y1<=y0 or x1<=x0: return
    crop=np.ascontiguousarray(delta[y0-y:y1-y,x0-x:x1-x])
    pipe.lip_makeup_delta=torch.tensor(crop,device=pipe.device).permute(2,0,1)[None]
    pipe.lip_makeup_local=(y0,x0,y1-y0,x1-x0)


def apply_delta(pipe,pixels):
    delta=getattr(pipe,'lip_makeup_delta',None)
    if delta is None: return pixels
    import torch
    y,x,h,w=pipe.lip_makeup_local
    output=pixels.clone(); current=pixels[:,:,y:y+h,x:x+w]
    output[:,:,y:y+h,x:x+w]=torch.where(delta!=0,(current+delta).clamp(0,1),current)
    return output
