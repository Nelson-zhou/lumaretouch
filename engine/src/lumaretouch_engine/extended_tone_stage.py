"""Full-frame before output clipping; preview scale is explicit, never inferred from a tile."""
from . import extended_tone_state as S
from .extended_tone_native import render

class ExtendedToneStage:
    def __init__(self, spec=None, *, scale=1., monochrome=False, mask=None, cancelled=lambda: False):
        self.spec = S.check(spec)
        self.scale, self.monochrome, self.mask = scale, monochrome, mask
        self.cancelled = cancelled
        self.active = any(S.effective(self.spec, monochrome))

    def apply_np(self, pixels):
        return render(pixels, self.spec, self.mask, self.scale, self.monochrome, self.cancelled)

    def apply_t(self, pixels):
        if not self.active: return pixels
        import torch
        import numpy as np
        if pixels.ndim != 4 or pixels.shape[1] != 3 or pixels.dtype != torch.float32:
            raise ValueError('Extended tone requires float32 N×3×H×W, not implicit half precision')
        # Explicit CPU bridge until a validated GPU implementation exists. No hidden inference.
        result = []
        for item in pixels.detach().cpu().numpy():
            rgb = np.ascontiguousarray(item.transpose(1, 2, 0))
            result.append(self.apply_np(rgb).transpose(2, 0, 1))
        return torch.from_numpy(np.ascontiguousarray(np.stack(result))).to(device=pixels.device)


    def finish_np(self, pixels):
        if not (self.spec['enabled'] and self.spec['monochrome']): return pixels
        from .extended_tone_native import monochrome
        return monochrome(pixels,self.cancelled)

    def finish_t(self, pixels):
        if not (self.spec['enabled'] and self.spec['monochrome']): return pixels
        import torch
        import numpy as np
        if pixels.ndim!=4 or pixels.shape[1]!=3 or pixels.dtype!=torch.float32:raise ValueError('Monochrome requires float32 NCHW')
        result=[self.finish_np(np.ascontiguousarray(item.transpose(1,2,0))).transpose(2,0,1) for item in pixels.detach().cpu().numpy()]
        return torch.from_numpy(np.ascontiguousarray(np.stack(result))).to(device=pixels.device)
