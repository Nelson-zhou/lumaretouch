"""E(N(B(A(x)))) composition; no serial RGB resampling or field addition."""
import numpy as np
from .brow_shape_field import BrowField,smoothstep
from .brow_shape_geometry import polygon_inside
from .nose_shape_field import edge_distance,compose_delta as previous_composition


class EyeField(BrowField):
    def __init__(self,P,D,meta,shape):
        self.protected=meta['protected']
        self.iris_only=meta['iris_only']
        super().__init__(P,D,{**meta,'sides':meta['controls']},shape)
        if self.state is not None:
            error=np.linalg.norm(self.evaluate(P)-D,axis=1)
            if np.any(error>max(.2,self.eye_width*.005)):
                raise ValueError('眼形与保护区冲突，未静默削弱请求')

    def _protection(self,X):
        factor=np.ones(len(X),np.float64)
        for poly in self.protected:
            inside=polygon_inside(X[:,0],X[:,1],poly)
            factor*=np.where(inside,0.,smoothstep(edge_distance(X,poly)/max(.5,self.eye_width*.025)))
        for poly,center,radius in self.iris_only:
            near=np.linalg.norm(X-center,axis=1)<radius
            inside=polygon_inside(X[:,0],X[:,1],poly)
            aperture=np.where(inside,smoothstep(edge_distance(X,poly)/max(.5,self.eye_width*.025)),0.)
            factor*=np.where(near,aperture,1.)
        return factor

    def _check_fold(self):
        try: super()._check_fold()
        except ValueError as error: raise ValueError('眼形叠加存在折叠风险，请减小强度') from error

    def resident_bytes(self):
        return super().resident_bytes()+sum(p.nbytes for p in self.protected)


def compose_delta(auto_delta,brow,nose,eye,shape,*,band_pixels=65536):
    if eye is None or eye.state is None:
        return previous_composition(auto_delta,brow,nose,shape,band_pixels=band_pixels)
    h,w=shape
    fields=[f for f in (brow,nose,eye) if f is not None and f.state is not None]
    if any(f.shape!=(h,w) for f in fields): raise ValueError('五官场与源图坐标帧不一致')
    if auto_delta is not None and tuple(auto_delta.shape) not in ((h,w,2),(1,h,w,2)):
        raise ValueError('自动形变场与眼形坐标帧不一致')
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
        if not np.isfinite(band).all(): raise ValueError('眼形组合场非有限')
        result[0,y:end]=band
        peak=max(peak,float(np.max(np.abs(band))))
    return result,peak
