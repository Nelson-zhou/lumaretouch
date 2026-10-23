"""Mix current edited pixels, not a cached source photograph, in linear sRGB."""
import numpy as np
from .optional_dependencies import optional_module

class IDBackgroundStage:
    def __init__(self, device, shape):
        self.device,self.shape=device,tuple(shape)
        self.fields=None; self.suspended=None; self.required=False
        self.spill_source=None; self.spill_window=None

    def install(self, prepared, window=None):
        torch=optional_module('torch')
        self.spill_source=None;self.spill_window=None
        alpha,background=prepared['alpha'],prepared['background']
        if window is not None:
            y0,x0,y1,x1=window;alpha=alpha[y0:y1,x0:x1];background=background[y0:y1,x0:x1]
        if alpha.shape!=self.shape or background.shape!=self.shape+(3,): raise ValueError('换背景场尺寸不匹配')
        if not np.isfinite(alpha).all() or not np.isfinite(background).all(): raise ValueError('换背景场无效')
        self.fields=torch.cat((torch.tensor(np.ascontiguousarray(alpha),device=self.device)[None,None],
            torch.tensor(np.ascontiguousarray(background.transpose(2,0,1)),device=self.device)[None]),dim=1)
        from .spill_removal_render import FIELD_KEYS, check_source_proof
        if FIELD_KEYS.intersection(prepared):
            from copy import deepcopy
            if not FIELD_KEYS.issubset(prepared):raise ValueError('缺少完整祛染色源图场')
            delta,confidence=prepared['spill_delta'],prepared['spill_confidence']
            domain=prepared['alpha'].shape
            check_source_proof(prepared['spill_source'],domain)
            if (type(delta) is not np.ndarray or delta.dtype!=np.float32 or delta.shape!=domain+(3,)
                    or type(confidence) is not np.ndarray or confidence.dtype!=np.float32 or confidence.shape!=domain):
                raise ValueError('祛染色场尺寸或精度不匹配')
            if window is not None:
                y0,x0,y1,x1=window;delta=delta[y0:y1,x0:x1];confidence=confidence[y0:y1,x0:x1]
            if (delta.shape!=self.shape+(3,) or confidence.shape!=self.shape
                    or not np.isfinite(delta).all() or not np.isfinite(confidence).all()
                    or np.any(confidence<0) or np.any(confidence>1)):
                raise ValueError('祛染色场无效')
            self.fields=torch.cat((self.fields,
                torch.tensor(np.ascontiguousarray(delta.transpose(2,0,1)),device=self.device)[None],
                torch.tensor(np.ascontiguousarray(confidence),device=self.device)[None,None]),dim=1)
            self.spill_source=deepcopy(prepared['spill_source'])
            self.spill_window=None if window is None else tuple(window)
        self.required=True

    def apply(self,rgb,align):
        if self.suspended: raise ValueError('证件照换背景已暂停：'+self.suspended)
        if not self.required:return rgb
        if self.fields is None:raise ValueError('缺少证件照换背景场')
        from .ops.matting import composite_linear_fields_t
        packed=align(self.fields)
        if self.spill_source is not None:
            from .spill_removal_render import apply_t
            if packed.shape[1]!=8:raise ValueError('缺少完整祛染色对齐场')
            rgb=apply_t(rgb,packed[:,4:7],packed[:,7:8])
            return composite_linear_fields_t(rgb,packed[:,:1],packed[:,1:4])
        return composite_linear_fields_t(rgb,packed[:,:1],packed[:,1:])
