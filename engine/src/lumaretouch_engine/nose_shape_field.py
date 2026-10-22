"""N(B(A(x))) source-domain pullbacks; one final RGB/mask sampler only.

Reuse mature TPS, bounded evaluation and compact support from BrowField. Nose
protection explicitly does NOT inherit that field's zero-displacement bridge.
"""
import numpy as np
from .brow_shape_field import BrowField,smoothstep,compose_delta as compose_brow_delta
from .brow_shape_geometry import EYES,polygon_inside
from .nose_shape_geometry import LIPS


def edge_distance(X,poly):
    result=np.full(len(X),np.inf)
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        d=b-a; den=float(d@d)
        if den<1e-10: continue
        t=np.clip(((X-a)@d)/den,0,1)
        result=np.minimum(result,np.linalg.norm(X-a-t[:,None]*d,axis=1))
    return result


class NoseField(BrowField):
    def __init__(self,P,D,meta,shape):
        self.nostrils=meta['nostrils']; self.width=meta['width']
        super().__init__(P,D,{**meta,'sides':meta['controls']},shape)
        if self.state is not None:
            error=np.linalg.norm(self.evaluate(P)-D,axis=1)
            if np.any(error>max(.2,self.width*.005)):
                raise ValueError('鼻形请求与保护区域冲突，未静默削弱或取消控件')

    def _protection(self,X):
        factor=np.ones(len(X),np.float64)
        clearance=max(.5,self.width*.035)
        for indices in (*EYES.values(),LIPS):
            poly=self.landmarks[list(indices)]
            inside=polygon_inside(X[:,0],X[:,1],poly)
            factor*=np.where(inside,0.,smoothstep(edge_distance(X,poly)/clearance))
        return factor

    def evaluate(self,points):
        X=np.asarray(points,dtype=np.float64)
        result=super().evaluate(X)
        if self.state is None: return result
        # Rigid pullback inside each translated aperture triangle, feathering
        # outward. This preserves source texture, not generated/missing tissue.
        for poly,move in self.nostrils:
            inside=polygon_inside(X[:,0],X[:,1],poly)
            mix=np.where(inside,1.,1-smoothstep(edge_distance(X,poly)/max(.5,self.width*.04)))
            result=result*(1-mix[:,None])+move*mix[:,None]
        result*=self._protection(X)[:,None]
        if not np.isfinite(result).all(): raise ValueError('鼻形 TPS 产出非有限位移')
        return result

    def _check_fold(self):
        try: super()._check_fold()
        except ValueError as error: raise ValueError('鼻形组合存在折叠风险，请减小强度') from error

    def resident_bytes(self):
        return super().resident_bytes()+sum(p.nbytes+d.nbytes for p,d in self.nostrils)


def compose_delta(auto_delta,brow,nose,shape,*,band_pixels=65536):
    """Return final (1,H,W,2) float32 and actual total component peak.

    Neutral nose delegates unchanged to the existing brow path. Do not feed an
    already brow-composed delta together with a brow field (double composition).
    No images or source masks are sampled in this function.
    """
    if nose is None or nose.state is None:
        return compose_brow_delta(auto_delta,brow,shape,band_pixels=band_pixels)
    h,w=shape
    fields=[field for field in (brow,nose) if field is not None and field.state is not None]
    if any(field.shape!=(h,w) for field in fields): raise ValueError('鼻形/眉形坐标帧与导出或预览不一致')
    if auto_delta is not None and tuple(auto_delta.shape) not in ((h,w,2),(1,h,w,2)):
        raise ValueError('自动形变场与鼻形坐标帧不一致')
    result=np.zeros((1,h,w,2),np.float32); peak=0.
    rows=max(1,int(band_pixels)//w)
    for y in range(0,h,rows):
        end=min(h,y+rows); yy,xx=np.mgrid[y:end,:w]
        X=np.stack((xx.ravel(),yy.ravel()),axis=1).astype(np.float64)
        total=np.zeros_like(X)
        if auto_delta is not None:
            block=auto_delta[0,y:end] if len(auto_delta.shape)==4 else auto_delta[y:end]
            if hasattr(block,'detach'): block=block.detach().to('cpu').numpy()
            total=np.asarray(block,np.float64).reshape(-1,2).copy()
            if not np.isfinite(total).all(): raise ValueError('自动形变场非有限')
        for field in fields:
            total+=field.evaluate(X-total)
        band=total.reshape(end-y,w,2).astype(np.float32)
        if not np.isfinite(band).all(): raise ValueError('鼻形组合场非有限')
        result[0,y:end]=band
        peak=max(peak,float(np.max(np.abs(band))))
    return result,peak
