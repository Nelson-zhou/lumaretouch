"""One-sample joint pullback: B(A(x)), never forward-field addition.

Automatic A(x)=x-D_auto(x) retains the existing engine semantics. Eyebrow B
is solved in source coordinates at target controls, B(q)=q-D_brow(q). Therefore
C(x)=B(A(x))=x-[D_auto(x)+D_brow(x-D_auto(x))]. Only C samples image/masks.
"""
import math
import numpy as np
from .ops.deform import tps_solve,tps_eval
from .brow_shape_geometry import EYES,BRIDGE,polygon_inside


def smoothstep(t):
    t=np.clip(t,0,1)
    return t*t*(3-2*t)


class BrowField:
    def __init__(self,P,D,meta,shape):
        self.shape=tuple(shape); self.facts=meta['sides']; self.merged=meta['merged']
        self.windows=meta['windows']; self.landmarks=meta['landmarks']
        self.state=tps_solve(P,D,scale=float(max(shape))) if self.windows else None
        # Dense kernels remain bounded to <= 2 million point/control pairs.
        self.batch=max(1,2_000_000//len(P))
        self.eye_width=min(np.linalg.norm(self.landmarks[33]-self.landmarks[133]),
                           np.linalg.norm(self.landmarks[263]-self.landmarks[362]))
        if self.state is not None: self._check_fold()

    def _protection(self,X):
        lm=self.landmarks; factor=np.ones(len(X),np.float64)
        clearance=max(.5,self.eye_width*.025)
        for indices in EYES.values():
            poly=lm[list(indices)]
            inside=polygon_inside(X[:,0],X[:,1],poly)
            distance=np.full(len(X),np.inf)
            for a,b in zip(poly,np.roll(poly,-1,axis=0)):
                d=b-a; den=float(d@d)
                if den<1e-10: continue
                t=np.clip(((X-a)@d)/den,0,1)
                distance=np.minimum(distance,np.linalg.norm(X-a-t[:,None]*d,axis=1))
            factor*=np.where(inside,0.,smoothstep(distance/clearance))
        for a,b in zip(lm[list(BRIDGE)][:-1],lm[list(BRIDGE)][1:]):
            d=b-a; den=float(d@d)
            if den<1e-10: continue
            t=np.clip(((X-a)@d)/den,0,1)
            distance=np.linalg.norm(X-a-t[:,None]*d,axis=1)
            factor*=smoothstep((distance-clearance)/clearance)
        return factor

    def evaluate(self,points):
        X=np.asarray(points,dtype=np.float64)
        if X.ndim!=2 or X.shape[1]!=2 or not np.isfinite(X).all(): raise ValueError('眉形求值坐标无效')
        result=np.zeros_like(X)
        if self.state is None: return result
        for start in range(0,len(X),self.batch):
            q=X[start:start+self.batch]; window=np.zeros(len(q))
            # Same compact smoothstep as ops.deform._window, evaluated at the
            # actual off-grid pullback points, not a re-interpolated dense field.
            for center,r0,R in self.windows:
                win=1-smoothstep((np.linalg.norm(q-center,axis=1)-r0)/max(R-r0,1e-9))
                window=np.maximum(window,win)
            window*=self._protection(q)
            active=window!=0
            if np.any(active):
                band=result[start:start+len(q)]
                band[active]=tps_eval(self.state,q[active])*window[active,None]
        if not np.isfinite(result).all(): raise ValueError('眉形 TPS 产出非有限位移')
        return result

    def _check_fold(self):
        # Conservative numerical admission, NOT proof of injectivity between
        # probes. Product photographic/grid acceptance remains a local test gate.
        eps=max(.05,max(self.shape)*1e-5)
        for center,_,radius in self.windows:
            yy,xx=np.mgrid[-1:1:33j,-1:1:33j]
            X=np.stack((xx.ravel(),yy.ravel()),axis=1)*radius+center
            dx=(self.evaluate(X+[eps,0])-self.evaluate(X-[eps,0]))/(2*eps)
            dy=(self.evaluate(X+[0,eps])-self.evaluate(X-[0,eps]))/(2*eps)
            det=(1-dx[:,0])*(1-dy[:,1])-dy[:,0]*dx[:,1]
            if np.any(det<.15): raise ValueError('眉形组合产生折叠风险，请减小强度')

    def resident_bytes(self):
        return self.landmarks.nbytes+sum(v.nbytes for v in (self.state or {}).values() if isinstance(v,np.ndarray))


def compose_delta(auto_delta,field,shape,*,band_pixels=65536):
    """Return CPU (1,H,W,2) float32 plus ACTUAL total component peak for halo.

    auto_delta may be a CPU/GPU tensor or ndarray. No RGB is sampled here.
    With no brow field return the exact input object (neutral compatibility).
    """
    if field is None or field.state is None:
        if auto_delta is None: return None,0.
        if hasattr(auto_delta,'detach'):
            return auto_delta,float(auto_delta.detach().abs().max().item())
        return auto_delta,float(np.max(np.abs(auto_delta)))
    h,w=shape
    if field.shape!=(h,w): raise ValueError('眉形场坐标帧与导出/预览不一致')
    if auto_delta is not None and tuple(auto_delta.shape) not in ((h,w,2),(1,h,w,2)):
        raise ValueError('自动形变场与眉形坐标帧不一致')
    acc=np.zeros((1,h,w,2),np.float32); peak=0.
    rows=max(1,int(band_pixels)//w)
    for y in range(0,h,rows):
        end=min(h,y+rows); yy,xx=np.mgrid[y:end,:w]
        X=np.stack((xx.ravel(),yy.ravel()),axis=1).astype(np.float64)
        if auto_delta is None: auto=np.zeros_like(X)
        else:
            block=auto_delta[0,y:end] if len(auto_delta.shape)==4 else auto_delta[y:end]
            if hasattr(block,'detach'): block=block.detach().to('cpu').numpy()
            auto=np.asarray(block,np.float64).reshape(-1,2)
            if not np.isfinite(auto).all(): raise ValueError('自动形变场非有限')
        joint=auto+field.evaluate(X-auto)
        band=joint.reshape(end-y,w,2).astype(np.float32)
        if not np.isfinite(band).all(): raise ValueError('合成形变场非有限')
        acc[0,y:end]=band
        peak=max(peak,float(np.max(np.abs(band))))
    return acc,peak
