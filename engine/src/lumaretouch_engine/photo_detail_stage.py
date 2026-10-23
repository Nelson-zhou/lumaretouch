"""Whole edited-canvas stage after geometry and global color operators and before final monochrome/quantization."""
from . import photo_detail_state as S
from .photo_detail_native import render
class PhotoDetailStage:
    def __init__(self,spec=None,*,scale=1.,cancelled=lambda:False):
        self.spec=S.check(spec);self.scale=scale;self.cancelled=cancelled;self.active=S.active(self.spec)
    def apply_np(self,pixels):return render(pixels,self.spec,scale=self.scale,cancelled=self.cancelled)
    def apply_t(self,pixels):
        if not self.active:return pixels
        import torch
        import numpy as np
        if pixels.ndim!=4 or pixels.shape[1]!=3 or pixels.dtype!=torch.float32:raise ValueError('Photo detail requires full float32 NCHW')
        result=[]
        for item in pixels.detach().cpu().numpy():
            result.append(self.apply_np(np.ascontiguousarray(item.transpose(1,2,0))).transpose(2,0,1))
        return torch.from_numpy(np.ascontiguousarray(np.stack(result))).to(device=pixels.device)
