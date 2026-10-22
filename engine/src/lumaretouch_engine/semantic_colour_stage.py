# SPDX-License-Identifier: GPL-3.0-or-later
"""Tiled full-resolution pointwise stage after geometry and PC32455.

CPU float32 production calls the very same Rust evaluator as fitting. Torch uses
an explicit CPU bridge, not an unverified second formula. Performance is UNRUN.
Masks stay on the bounded analysis grid until each 512² output tile is evaluated.
"""
import numpy as np
from . import semantic_colour_state as S, semantic_colour_native as N, semantic_colour_masks as M

class SemanticColourStage:
    def __init__(self,recipe,*,binding=None):
        self.recipe=S.check(recipe);self.active=S.active(self.recipe);self.suspension=None
        if self.active and binding is not None:
            p=self.recipe['target'];b=S.binding(binding)
            if (p['source'],p['geometry_sha256'],p['width'],p['height']) != (b['source'],b['geometry_sha256'],b['width'],b['height']):
                self.suspension='AI 追色因源图、素材归属或几何变化暂停；保留参数和蒙版，请重新分析审核'

    def apply_np(self,pixels,*,strict=True):
        if not self.active:return pixels
        if self.suspension:
            if strict:raise ValueError(self.suspension)
            return pixels
        if type(pixels) is not np.ndarray or pixels.ndim!=3 or pixels.shape[-1]!=3 or pixels.dtype not in (np.uint8,np.uint16,np.float32):
            raise ValueError('AI 追色需要真实 RGB8/16/float32 画布')
        h,w=pixels.shape[:2]
        if h*w>S.MAX_PIXELS:raise ValueError('AI 追色完整输出超过预算')
        from .cpu_memory_budget import available_estimate
        if available_estimate()<pixels.nbytes+128*1024*1024:raise ValueError('AI 追色最终画布内存预算不足；不会缩小导出分辨率')
        integer=pixels.dtype.kind=='u';scale=np.iinfo(pixels.dtype).max if integer else 1.
        groups=[g for g in self.recipe['groups'] if g['enabled']]
        global_group=next((g for g in groups if g['id']=='global'),None)
        local=[g for g in groups if g['id']!='global' and g['parameters']!=S.neutral()]
        masks={m['id']:m for m in self.recipe['masks']};compiled=[];success=False
        try:
            for g in local:compiled.append(M.TileMask(masks[g['mask_id']],(h,w)))
            out=np.empty_like(pixels)
            for y in range(0,h,512):
                for x in range(0,w,512):
                    tile=pixels[y:y+512,x:x+512];th,tw=tile.shape[:2]
                    if not np.isfinite(tile).all():raise ValueError('AI 追色输入包含非有限像素')
                    base=np.asarray(tile,dtype=np.float32)/scale
                    if global_group:base=N.apply(base,global_group['parameters'],self.recipe['strengths'])
                    fields=[mask.tile(x,y,tw,th) for mask in compiled]
                    if fields:
                        total=np.maximum(np.sum(fields,axis=0),1.);delta=np.zeros(base.shape,np.float64)
                        for g,field in zip(local,fields):
                            # Every local residual evaluates the SAME global base.
                            # Normalized overlap conserves total mask coverage<=1.
                            weight=field/total
                            changed=N.apply(base,g['parameters'],self.recipe['strengths'],weight)
                            # Native performs the exact masked float32 endpoint.
                            # Accumulate parallel residuals in float64, so one
                            # local group remains bit-identical to that endpoint.
                            delta+=changed.astype(np.float64)-base
                        value=np.where(delta!=0,base+delta,base)
                    else:value=base
                    if integer:value=np.clip(np.rint(value*scale),0,scale)
                    out[y:y+th,x:x+tw]=value.astype(pixels.dtype)
            success=True;return out
        finally:
            for mask in compiled:mask.close(success)

    def apply_t(self,pixels,*,strict=True):
        if not self.active:return pixels
        if self.suspension and not strict:return pixels
        import torch
        if pixels.ndim!=4 or pixels.shape[0]!=1 or pixels.shape[1]!=3 or not pixels.is_floating_point():raise ValueError('AI 追色 Torch 需要单画布 NCHW 浮点 RGB')
        from .cpu_memory_budget import available_estimate
        required=pixels.numel()*4*2+128*1024*1024
        if available_estimate()<required:raise ValueError('AI 追色 CPU 浮点桥内存预算不足；不会降低输出精度或分辨率')
        array=pixels.detach().to(device='cpu',dtype=torch.float32).permute(0,2,3,1)[0].contiguous().numpy()
        out=self.apply_np(array,strict=strict)
        return torch.from_numpy(np.ascontiguousarray(out)).permute(2,0,1)[None].to(device=pixels.device,dtype=torch.float32)
