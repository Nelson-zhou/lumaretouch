"""Composed inverse remap at full raster coordinates, float source preserved.

Each output band reads any required source pixels from the complete upstream
raster. This stage is NOT executed independently inside legacy upstream tiles.
"""
import time
import numpy as np
from . import optics_state as S
from .optics_perspective import matrix, validate_matrix
from .optics_native import grid, sample
from .optics_lensfun import LensProfile


def linear(value):
    return np.where(value<=.04045,value/12.92,np.maximum((value+.055)/1.055,0)**2.4)


def encoded(value):
    return np.where(value<=.0031308,value*12.92,1.055*np.maximum(value,0)**(1/2.4)-.055)


class OpticsStage:
    def __init__(self, value=None, shape=None):
        self.value = S.check(value); self.shape = None if shape is None else tuple(shape)
        self.suspended = None; self.last_ms = 0.; self.profile = None; self.zoom = 1.
        self.inverse = None
        if shape is not None and S.active(self.value): self.prepare(shape)

    def prepare(self, shape):
        h,w = shape
        if type(h) is not int or type(w) is not int or not 1<=h*w<=64_000_000 or max(h,w)>65536: raise ValueError('镜头/透视图幅超过预算')
        from .optics_native import native
        native()  # explicit preflight before a profile is reported as enabled
        self.shape = tuple(shape)
        self.inverse = np.linalg.inv(matrix(self.value,shape))
        lens = self.value['lens']
        self.profile = LensProfile(lens['profile'],shape) if lens['enabled'] else None
        if self.profile:
            from .cpu_memory_budget import available_estimate
            if h*w*24+768*1024*1024>available_estimate(): raise ValueError('镜头配置场超过可用内存预算')
            self.profile.gains()
        p = self.value['perspective']
        lens_active = bool(lens['enabled'] or lens['distortion'])
        perspective_active = bool(p['matrix'] != S.IDENTITY or any(p[k]!=d for k,d in S.MANUAL.items()))
        if lens_active and lens['crop_lock'] or perspective_active and p['crop_lock']:
            self.zoom = self._crop_zoom()
        return self

    def _point_map(self, points, zoom):
        h,w = self.shape
        v = np.column_stack([points/zoom,np.ones(len(points))])@self.inverse.T
        q = v[:,:2]/v[:,2:]
        radius = (q[:,0]**2*w*w+q[:,1]**2*h*h)/(w*w+h*h)
        q *= (1+self.value['lens']['distortion']*.002*radius)[:,None]
        pixels = (q+1)*np.array([w,h])/2-.5
        if self.profile and any(k in self.profile.value['flags'] for k in ('distortion','tca')):
            return self.profile.points(pixels)
        return pixels[:,None,:]

    def _crop_zoom(self):
        # Convex homography and monotone manual radial model use all edge
        # samples. Lensfun profiles get interior probes too. Rendering checks
        # the complete resulting map, so an unusual folded profile fails closed.
        t = np.linspace(-1.,1.,65)
        points = np.concatenate([np.column_stack([t,np.full_like(t,k)]) for k in (-1.,1.)]+
                                [np.column_stack([np.full_like(t,k),t]) for k in (-1.,1.)]+
                                [np.array([[x,y] for x in np.linspace(-1,1,9) for y in np.linspace(-1,1,9)])])
        h,w = self.shape
        def fits(zoom):
            q = self._point_map(points,zoom)
            return np.isfinite(q).all() and np.all(q[...,0]>=-.5000001) and np.all(q[...,0]<=w-.4999999) and np.all(q[...,1]>=-.5000001) and np.all(q[...,1]<=h-.4999999)
        if fits(1.): return 1.
        hi = 1.05
        while hi < 32 and not fits(hi): hi *= 1.25
        if hi > 32 or not fits(hi): raise ValueError('无法在原比例内安全锁定裁剪，请减小偏移/透视或关闭锁定裁剪')
        lo = 1.
        for _ in range(18):
            mid = (lo+hi)/2
            if fits(mid): hi = mid
            else: lo = mid
        return hi*(1+1e-6)

    def coordinates(self, *, y0=0, rows=None):
        if self.inverse is None: self.prepare(self.shape)
        xy = grid(self.shape,self.inverse,self.value['lens']['distortion'],self.zoom,y0=y0,rows=rows)
        return self.profile.coordinates(xy) if self.profile else np.repeat(xy[...,None,:],3,axis=-2)

    def inverse_points(self, points):
        """Final optical normalized edge positions -> pre-optics coordinates.

        Green-channel geometry is the unique control coordinate when TCA differs
        by channel. This does not invert automatic/manual upstream deformation.
        """
        if not S.active(self.value): return np.asarray(points,np.float64)
        result = self._point_map(np.asarray(points,np.float64)*2-1,self.zoom)
        green = result[:,1 if result.shape[1]>1 else 0]
        h,w = self.shape
        out = (green+.5)/np.array([w,h])
        if not np.isfinite(out).all() or np.any(out<0) or np.any(out>1): raise ValueError('控制点落在镜头/透视补边，已取消操作')
        return out

    def apply_np(self, pixels, *, cancelled=lambda:False):
        self.last_ms = 0.
        if self.suspended: raise ValueError('镜头/透视已暂停：'+self.suspended)
        if not S.active(self.value): return pixels
        if tuple(pixels.shape[:2]) != self.shape or pixels.ndim != 3 or pixels.shape[2] != 3: raise ValueError('镜头/透视输入画布不匹配')
        from .cpu_memory_budget import available_estimate
        h,w = self.shape
        # Source, linearized source, output, Lensfun gains and maximum map band.
        budget = h*w*(24+24+pixels.dtype.itemsize*3+(24 if self.profile else 0))+(768 if self.profile else 128)*1024*1024
        if budget>available_estimate(): raise ValueError('镜头/透视内存预算不足；不会降位深或用放大的代理出片')
        start = time.perf_counter(); maximum = np.iinfo(pixels.dtype).max if np.issubdtype(pixels.dtype,np.integer) else 1.
        source = np.array(pixels,dtype=np.float64,order='C',copy=True)
        if maximum!=1: source /= maximum
        if not np.isfinite(source).all(): raise ValueError('镜头/透视输入包含非有限值')
        gain = self.profile.gains() if self.profile else None
        vignette = self.value['lens']['vignette']
        if gain is not None or vignette:
            for y in range(0,h,64): source[y:y+64] = linear(source[y:y+64])
            if gain is not None: source *= gain
            if vignette:
                # Midpoint controls the vignette's radial onset. It is not
                # disguised perspective or a change to crop/rotation settings.
                midpoint = self.value['lens']['midpoint']/100*.9
                for y in range(0,h,64):
                    yy,xx = np.mgrid[y:min(h,y+64),0:w]
                    r = np.sqrt(((2*xx+1-w)**2+(2*yy+1-h)**2)/(w*w+h*h))
                    f = np.clip((r-midpoint)/(1-midpoint),0,1); f = f*f*(3-2*f)
                    source[y:y+len(yy)] *= np.exp2(vignette*.02*f)[...,None]
            # Linear-light gains are applied before geometric sampling. Keep
            # linear RGB through the interpolation, then encode exactly once.
        output = np.empty_like(pixels)
        lens=self.value['lens'];perspective=self.value['perspective']
        lock = ((lens['enabled'] or lens['distortion']) and lens['crop_lock']) or ((perspective['matrix']!=S.IDENTITY or any(perspective[k]!=d for k,d in S.MANUAL.items())) and perspective['crop_lock'])
        rows = max(1,min(64,1_048_576//w))
        for y in range(0,h,rows):
            if cancelled(): raise InterruptedError('镜头/透视渲染已取消')
            count = min(rows,h-y); coords = self.coordinates(y0=y,rows=count)
            valid = np.isfinite(coords).all(axis=-1)&(coords[...,0]>=-.5)&(coords[...,0]<=w-.5)&(coords[...,1]>=-.5)&(coords[...,1]<=h-.5)
            if lock and not np.all(valid): raise ValueError('当前镜头标定未能在锁定裁剪内覆盖全部像素，请换配置或关闭锁定裁剪')
            result = np.empty((count,w,3),np.float64)
            for channel in range(3): result[...,channel] = sample(source,coords[...,channel,:])[...,channel]
            if gain is not None or vignette: result = encoded(result)
            if maximum != 1: result = np.rint(np.clip(result,0,1)*maximum)
            if not np.isfinite(result).all(): raise ValueError('镜头/透视结果无效')
            output[y:y+count] = result.astype(pixels.dtype)
        self.last_ms = (time.perf_counter()-start)*1000
        return output

    def apply(self, tensor):
        if self.suspended: raise ValueError('镜头/透视已暂停：'+self.suspended)
        if not S.active(self.value): return tensor
        import torch
        array = tensor[0].permute(1,2,0).detach().cpu().numpy()
        output = self.apply_np(array)
        return torch.as_tensor(output,device=tensor.device,dtype=tensor.dtype).permute(2,0,1)[None]

    def resident_bytes(self):
        return 0 if self.profile is None or self.profile.gain is None else self.profile.gain.nbytes
