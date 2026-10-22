"""Prepared linear sky samples and source-domain region fields for one tile."""
import time
import numpy as np
from . import sky_replacement_state as S
from .optional_dependencies import optional_module
from .ops import sky_replacement as O


class SkyReplacementStage:
    def __init__(self, device, shape):
        self.device, self.shape = device, tuple(shape)
        self.value = S.empty()
        self.fields = {}
        self.sky = self.reflection = self.tint = self.horizon_weight = None
        self.sky_valid = self.reflection_valid = None
        self.suspended = None
        self.asset_stamp = None
        self.last_ms = 0.

    def set(self, value, prepared=None, *, window=None, reason=None):
        value = S.check(value)
        self.value, self.suspended = value, reason
        self.asset_stamp = None
        self.fields = {}
        self.sky = self.reflection = self.tint = self.horizon_weight = None
        self.sky_valid = self.reflection_valid = None
        if reason or not value['enabled']:
            return
        S.ready(value)
        if prepared is None or prepared['value'] != value:
            raise ValueError('已启用换天空，但缺少对应素材与区域场')
        self.asset_stamp = prepared['asset_stamp']
        torch = optional_module('torch')
        if torch is None:
            raise ValueError('换天空浮点渲染需要 PyTorch')
        h, w = prepared['shape']
        y0, x0, y1, x1 = window or (0, 0, h, w)
        if (y1-y0, x1-x0) != self.shape or not (0 <= y0 < y1 <= h and 0 <= x0 < x1 <= w):
            raise ValueError('天空瓦片与整幅坐标域不一致')
        from .sky_replacement_export import admit_stage
        admit_stage(self.device,self.shape)
        params = value['parameters']
        sky, sky_valid = O.sample(prepared['asset'], params, (h, w), (y0,x0,y1,x1), prepared['cover'])
        reflection, reflection_valid = (sky, sky_valid)
        if params['reflection'] > 0:
            reflection, reflection_valid = O.sample(prepared['reflection'], params, (h,w), (y0,x0,y1,x1), prepared['cover'], horizon=value['horizon'])
        to_tensor = lambda a: torch.as_tensor(np.ascontiguousarray(a), device=self.device)
        self.sky = to_tensor(sky).permute(2,0,1)[None]
        self.reflection = to_tensor(reflection).permute(2,0,1)[None]
        self.tint = to_tensor(prepared['tint']).reshape(1,3,1,1)
        self.fields = {key: to_tensor(array[y0:y1,x0:x1])[None,None].to(torch.float32)
                       for key, array in prepared['fields'].items()}
        self.sky_valid = to_tensor(sky_valid)[None,None]
        self.reflection_valid = to_tensor(reflection_valid)[None,None]
        # Plane is source-domain, just like the user's water selection. It is
        # clipped BEFORE the same real warp as every other source field.
        horizon = value['horizon']
        plane = np.zeros((y1-y0,1), np.float32) if horizon is None else ((np.arange(y0,y1)+.5)/h >= horizon).astype(np.float32)[:,None]
        self.horizon_weight = to_tensor(plane)[None,None]

    def apply(self,pixels,align_source_mask):
        try: return self._apply(pixels,align_source_mask)
        except Exception as error:
            self.suspended=str(error)[:2000]
            raise

    def _apply(self, pixels, align_source_mask):
        self.last_ms = 0.
        if self.suspended:
            raise ValueError('换天空已暂停：'+self.suspended)
        if not self.value['enabled']:
            return pixels
        if tuple(pixels.shape) != (1,3,*self.shape) or self.sky is None or set(self.fields) != {'sky','person','water','recovery'}:
            raise ValueError('换天空渲染输入与已验证区域不一致')
        torch = optional_module('torch')
        started = time.perf_counter()
        p = self.value['parameters']
        # One mature warp aligns masks, replacement pixels and valid coverage
        # together. This also keeps the explicit horizon coherent with a source
        # selection when upstream automatic body/face geometry moves its edge.
        packed = torch.cat([self.fields['sky'],self.fields['person'],
                            self.fields['water']*self.horizon_weight,self.fields['recovery'],
                            self.sky,self.reflection,self.sky_valid.to(torch.float32),
                            self.reflection_valid.to(torch.float32)],dim=1)
        aligned = align_source_mask(packed)
        fields = {key:aligned[:,i:i+1].clamp(0,1) for i,key in enumerate(('sky','person','water','recovery'))}
        sky,reflection = aligned[:,4:7],aligned[:,7:10]
        # Validate after the actual automatic warp. Missing transformed asset
        # pixels cannot become black fill, a border smear, or silent fallback.
        if p['opacity'] > 0:
            protected = (1-fields['person'])*(1-fields['recovery'])
            selected = fields['sky']*protected
            if torch.any((selected > 0) & (aligned[:,10:11] < 1-1e-6)):
                raise ValueError('当前天空位置或角度使素材露空，请放大或移回素材')
            if p['reflection'] > 0:
                water = fields['water']*protected*(1-fields['sky']*(p['opacity']/100.))
                if torch.any((water > 0) & (aligned[:,11:12] < 1-1e-6)):
                    raise ValueError('当前地平线或素材变换使水面反射采样超出素材，请调整')
        out = O.compose(pixels, sky, reflection, self.tint, fields, p,
                        horizon_weight=1., align=lambda value:value)
        self.last_ms = (time.perf_counter()-started)*1000.
        return out

    def resident_bytes(self):
        values = [*self.fields.values(), self.sky, self.reflection, self.tint, self.horizon_weight, self.sky_valid, self.reflection_valid]
        return sum(int(v.numel()*v.element_size()) for i,v in enumerate(values) if v is not None and all(v is not old for old in values[:i]))
