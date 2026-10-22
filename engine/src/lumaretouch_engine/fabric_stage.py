"""Measured fine fabric shading, with a GPU-only per-frame gain stage.

No garment synthesis or inferred clothing region. Support comes exclusively from
MediaPipe's clothes class; outside that support pixels stay bit-identical.
"""
from __future__ import annotations
import math
import numpy as np
from .optional_dependencies import optional_module

def check_amount(value=0.0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('衣物细褶强度必须是数值')
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('衣物细褶强度必须在 0 到 1 之间')
    return value

def clothing_mask(pc):
    if pc is None or getattr(pc, 'backend', None) == 'synthetic':
        return None
    return (getattr(pc, 'masks', None) or {}).get('clothes')

def face_scale(pc, h, w):
    pool = getattr(pc, 'all_landmarks', None) or [getattr(pc, 'landmarks', None)]
    widths = []
    for lm in pool:
        if lm is None:
            continue
        points = np.asarray(lm)
        if points.ndim == 2 and len(points) > 454:
            widths.append(float(np.linalg.norm((points[234, :2] - points[454, :2]) * [w, h])))
    return max(1.0, float(np.median(widths))) if widths else None

def measure_field(rgb, mask, face_px=None):
    """Measure on a complete image, never independently on export tiles."""
    import cv2
    from .ops.fabric import measure
    rgb = np.asarray(rgb, dtype=np.float32)
    if rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 2 or not np.isfinite(rgb).all():
        raise ValueError('衣物细褶需要有效 RGB 图像')
    if mask is None:
        raise ValueError('衣物语义蒙版不可用，请先完成人像分析')
    mask = np.asarray(mask, dtype=np.float32)
    if mask.shape != rgb.shape[:2] or not np.isfinite(mask).all() or np.any(mask < 0) or np.any(mask > 1):
        raise ValueError('衣物语义蒙版尺寸或概率无效')
    # Only shrink support. Blur must not introduce an editable halo into skin.
    radius = max(1, round(max(mask.shape) * 0.0015))
    support = cv2.erode((mask > 0).astype(np.uint8), np.ones((2 * radius + 1,) * 2, np.uint8))
    safe = mask * support
    if not np.any(safe > 1e-3):
        raise ValueError('未找到可信的衣物区域；不会改动皮肤或背景')
    corr = measure(rgb, safe, face_px)
    if corr is None:
        raise ValueError('未找到可处理的衣物区域')
    field = np.zeros(mask.shape, np.float32)
    y0, y1, x0, x1 = corr.box
    field[y0:y1, x0:x1] = corr.change
    # Enforce exact isolation after every upstream filtering operation.
    field[safe <= 0] = 0
    if not np.isfinite(field).all():
        raise ValueError('衣物细褶计算产生无效结果')
    return field

class FabricStage:
    def __init__(self, device):
        self.device = device
        self.amount = 0.0
        self.field = None
        self.key = None

    def clear(self):
        self.amount = 0.0
        self.field = None
        self.key = None

    def install(self, field, amount):
        torch = optional_module('torch')
        self.amount = check_amount(amount)
        self.field = torch.as_tensor(np.ascontiguousarray(field), device=self.device)[None, None]

    def apply(self, rgb):
        if self.amount == 0 or self.field is None:
            return rgb
        torch = optional_module('torch')
        base = rgb.clamp(0, 1)
        linear = torch.where(base <= .04045, base / 12.92, ((base + .055) / 1.055).pow(2.4))
        gain = torch.exp((self.field * self.amount).clamp(-1.5 * math.log(2), 1.5 * math.log(2)))
        cap = torch.maximum(torch.ones_like(gain), 1 / linear.amax(dim=1, keepdim=True).clamp_min(1e-4))
        out = (linear * torch.minimum(gain, cap)).clamp(0, 1)
        out = torch.where(out <= .0031308, out * 12.92, 1.055 * out.pow(1 / 2.4) - .055)
        return torch.where(self.field != 0, out, rgb)
