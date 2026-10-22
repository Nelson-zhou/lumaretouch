"""Final pre-geometry inverse warp using the existing mature Torch sampler."""
import time
import numpy as np
from .optional_dependencies import optional_module


def check_field(value, shape=None):
    if value is None: return None
    if (type(value) is not np.ndarray or value.dtype != np.float32 or value.ndim != 3 or value.shape[2] != 3
            or shape is not None and value.shape[:2] != tuple(shape)
            or not np.isfinite(value).all() or np.any(np.abs(value[..., :2]) > 65536)
            or np.any((value[..., 2] < 0) | (value[..., 2] > 1))):
        raise ValueError('手动液化位移或保护场缺失/损坏')
    return value


class ManualLiquifyStage:
    def __init__(self, device, shape, high_precision=False):
        self.device, self.shape, self.high_precision = device, tuple(shape), high_precision
        self.field = None
        self.prepared = None
        self.suspended = None
        self.last_ms = 0.

    def set(self, value, *, required=False, reason=None):
        self.field, self.prepared, self.suspended = None, None, reason
        if reason: return
        check_field(value, self.shape)
        if required and value is None:
            raise ValueError('已保留液化笔迹，但缺少正确重放的场；不允许忽略笔迹')
        self.field = value

    def apply(self, pixels):
        self.last_ms = 0.
        if self.suspended:
            raise ValueError('手动液化已暂停：'+self.suspended)
        if self.field is None or not np.any(self.field[..., :2]): return pixels
        if tuple(pixels.shape[-2:]) != self.shape:
            raise ValueError('手动液化像素不属于原定画布')
        torch = optional_module('torch')
        from .ops.deform import identity_grid, prepare_warp_t, apply_prepared_warp_t
        t0 = time.perf_counter()
        if self.prepared is None:
            dtype = torch.float64 if self.high_precision else torch.float32
            delta = torch.as_tensor(np.ascontiguousarray(self.field[..., :2]), device=self.device, dtype=dtype)[None]
            h, w = self.shape
            base = identity_grid(h, w, self.device, dtype=dtype)
            self.prepared = prepare_warp_t(delta, h, w, strength=-1., base=base)
        sample = pixels.to(torch.float64) if self.high_precision else pixels
        out = apply_prepared_warp_t(sample, self.prepared).to(pixels.dtype)
        if not torch.isfinite(out).all(): raise ValueError('液化输出包含非有限像素')
        self.last_ms = (time.perf_counter()-t0)*1000
        return out

    def resident_bytes(self):
        return (0 if self.field is None else int(self.field.nbytes)) + (0 if self.prepared is None else sum(int(t.numel()*t.element_size()) for t in self.prepared))
