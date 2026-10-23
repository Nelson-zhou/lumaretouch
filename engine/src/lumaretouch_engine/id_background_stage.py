"""Mix current edited pixels, not a cached source photograph, in linear sRGB."""
import numpy as np
from .optional_dependencies import optional_module

class IDBackgroundStage:
    def __init__(self, device, shape):
        self.device,self.shape=device,tuple(shape)
        self.fields=None; self.suspended=None; self.required=False

    def install(self, prepared, window=None):
        torch=optional_module('torch')
        alpha,background=prepared['alpha'],prepared['background']
        if window is not None:
            y0,x0,y1,x1=window;alpha=alpha[y0:y1,x0:x1];background=background[y0:y1,x0:x1]
        if alpha.shape!=self.shape or background.shape!=self.shape+(3,): raise ValueError('换背景场尺寸不匹配')
        if not np.isfinite(alpha).all() or not np.isfinite(background).all(): raise ValueError('换背景场无效')
        self.fields=torch.cat((torch.tensor(np.ascontiguousarray(alpha),device=self.device)[None,None],
            torch.tensor(np.ascontiguousarray(background.transpose(2,0,1)),device=self.device)[None]),dim=1)
        self.required=True

    def apply(self,rgb,align):
        if self.suspended: raise ValueError('证件照换背景已暂停：'+self.suspended)
        if not self.required:return rgb
        if self.fields is None:raise ValueError('缺少证件照换背景场')
        torch=optional_module('torch');packed=align(self.fields)
        a=packed[:,:1].clamp(0,1);bg=packed[:,1:]
        linear=torch.where(rgb<=0.04045,rgb/12.92,((rgb+0.055)/1.055).clamp_min(0).pow(2.4))
        mixed=linear*a+bg*(1-a)
        encoded=torch.where(mixed<=0.0031308,mixed*12.92,1.055*mixed.clamp_min(0).pow(1/2.4)-0.055)
        return torch.where(a>=1,rgb,encoded)
