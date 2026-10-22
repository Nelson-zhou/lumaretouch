"""Final colour-only transform, before output clipping/encoding/watermark.

Full floating working domain; no blur, geometry, 8-bit LUT or detail synthesis.
The extended sRGB equations mirror core/curves/curve.rs. Rust fits the constants;
NumPy/Torch vector operators apply them without CPU image loops/downloads.
"""
import numpy as np
from . import reference_color_state as S


class ReferenceColorStage:
    def __init__(self,recipe):
        self.recipe=S.check(recipe)
        self.active=S.active(self.recipe)
        self.gains=np.exp2(np.array(self.recipe['log2_gains'],np.float64)*self.recipe['strength'])

    def apply_np(self,pixels):
        if not self.active: return pixels  # Exact neutral including RGB16, no helper dependency.
        if not isinstance(pixels,np.ndarray) or pixels.ndim!=3 or pixels.shape[-1]!=3:
            raise ValueError('参考色彩需要 H×W×3 RGB')
        integer=pixels.dtype in (np.dtype('uint8'),np.dtype('uint16'))
        if not integer and pixels.dtype not in (np.dtype('float32'),np.dtype('float64')):
            raise ValueError('参考色彩不支持此像素类型')
        if not np.isfinite(pixels).all(): raise ValueError('参考色彩像素非有限')
        scale=np.iinfo(pixels.dtype).max if integer else 1.
        rgb=pixels.astype(np.float64 if pixels.dtype==np.float64 else np.float32)/scale
        a=np.abs(rgb)
        linear=np.sign(rgb)*np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)
        linear*=self.gains.astype(linear.dtype)
        a=np.abs(linear)
        result=np.sign(linear)*np.where(a<=.0031308,12.92*a,1.055*a**(1/2.4)-.055)
        if integer: result=np.clip(np.rint(result*scale),0,scale)
        return result.astype(pixels.dtype)

    def apply_t(self,pixels):
        if not self.active: return pixels
        import torch
        if pixels.ndim!=4 or pixels.shape[1]!=3 or not pixels.is_floating_point():
            raise ValueError('参考色彩 Torch 需要 N×3×H×W 浮点 RGB')
        # Keep float32 precision even when an upstream inference tensor is half.
        dtype=pixels.dtype;rgb=pixels.float() if dtype in (torch.float16,torch.bfloat16) else pixels
        gain=torch.as_tensor(self.gains,dtype=rgb.dtype,device=rgb.device)[None,:,None,None]
        a=rgb.abs();linear=rgb.sign()*torch.where(a<=.04045,a/12.92,((a+.055)/1.055).pow(2.4))*gain
        a=linear.abs()
        return linear.sign()*torch.where(a<=.0031308,12.92*a,1.055*a.pow(1/2.4)-.055)
