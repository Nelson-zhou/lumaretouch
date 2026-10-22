"""PC-32476 deterministic, float sky composition using mature vector operators.

OpenCV resize/remap/GaussianBlur/distanceTransform are Apache-2.0. Torch tensor
operators implement sRGB transfer and per-pixel linear-light compositing. No
scalar image loops, no uint8 RGB staging, and no claim of semantic detection.
"""
import math
import numpy as np
from ..optional_dependencies import optional_module


def _cv():
    cv=optional_module('cv2')
    if cv is None:
        raise ValueError('换天空需要项目的 OpenCV 运行依赖；未安装时不提供假效果')
    return cv


def linear(rgb):
    rgb = np.asarray(rgb, np.float32)
    return np.where(rgb <= .04045, rgb / 12.92, np.power((rgb + .055) / 1.055, 2.4)).astype(np.float32)


def adjusted_asset(pixels, p, shape):
    """Photometry and blur in asset space, once, before global-coordinate sampling."""
    cv = _cv()
    if pixels.dtype not in (np.uint8, np.uint16):
        raise ValueError('天空素材必须来自经验证的 RGB8 或 RGB16 原件')
    a = linear(pixels.astype(np.float32) / np.iinfo(pixels.dtype).max)
    luma = np.array([.2126, .7152, .0722], np.float32)
    gains = np.exp(np.array([p['temperature'] * .004, -p['tint'] * .003, -p['temperature'] * .004], np.float32))
    gains /= float(gains @ luma)
    a *= gains
    gray = np.sum(a * luma, axis=2, keepdims=True)
    a = np.clip((gray + (a - gray) * (1 + p['saturation'] / 100.)) * 2.**(p['brightness'] / 50.), 0, 1)
    # Normalize by full canvas, not an export tile or UI pixel width.
    h, w = shape
    ah, aw = a.shape[:2]
    theta = math.radians(p['angle'])
    cover = max((abs(math.cos(theta))*w+abs(math.sin(theta))*h)/aw,
                (abs(math.sin(theta))*w+abs(math.cos(theta))*h)/ah) * p['scale']/100.
    sigma = p['blur'] / 100. * min(h, w) * .03 / cover
    if sigma > .01:
        a = cv.GaussianBlur(a, (0, 0), sigma, borderType=cv.BORDER_REFLECT_101)
    mean = np.mean(a, axis=(0, 1), dtype=np.float64)
    if float(mean @ luma) < 1e-7:
        tint = np.ones(3, np.float32)
    else:
        tint = np.clip(mean / float(mean @ luma), .25, 4.).astype(np.float32)
    reflection = a
    sigma = p['reflection_blur'] / 100. * min(h, w) * .05 / cover
    if sigma > .01:
        reflection = cv.GaussianBlur(a, (0, 0), sigma, sigmaY=max(.01, sigma*.4), borderType=cv.BORDER_REFLECT_101)
    return np.ascontiguousarray(a), np.ascontiguousarray(reflection), tint, cover


def sky_edge(mask, p):
    """Signed-distance edge shift and spatial transition, full grid only."""
    cv = _cv()
    a = mask.astype(np.float32)/255.
    shift = p['edge'] / 100. * min(mask.shape) * .01
    if abs(shift) > .001:
        peak = float(a.max())
        inside = (a >= max(1/255.,peak*.5)).astype(np.uint8)
        if not np.any(inside) or np.all(inside):
            raise ValueError('天空边缘调整需要有效边界，不允许全图替代天空')
        signed = cv.distanceTransform(inside, cv.DIST_L2, cv.DIST_MASK_PRECISE) - cv.distanceTransform(1-inside, cv.DIST_L2, cv.DIST_MASK_PRECISE)
        a = np.clip(.5 + signed + shift, 0, 1)*peak
    sigma = p['gradient']/100. * min(mask.shape) * .02
    if sigma > .01:
        a = cv.GaussianBlur(a, (0, 0), sigma, borderType=cv.BORDER_REPLICATE)
    return np.ascontiguousarray(np.clip(a, 0, 1), dtype=np.float32)


def sample(asset, p, shape, window, cover, *, horizon=None):
    """One inverse affine in full-image coordinates; tile boundaries are irrelevant.

    Reflection mirrors about the explicitly supplied source-canvas horizon. The
    caller clips it to the marked water and below-horizon plane. Transparent
    outside-asset samples are rejected if selected, not filled with a fake sky.
    """
    cv = _cv()
    h, w = shape
    y0, x0, y1, x1 = window
    ah, aw = asset.shape[:2]
    if max(ah,aw,y1-y0,x1-x0)>=32767:
        raise ValueError('天空采样超过 OpenCV 单次坐标预算，请使用更小导出瓦片；不会缩小原片')
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    if horizon is not None:
        yy = 2 * (horizon*h - .5) - yy
    xx -= (w-1)/2 + p['horizontal']/100.*w
    yy -= (h-1)/2 + p['vertical']/100.*h
    theta = math.radians(p['angle'])
    c, s = math.cos(theta), math.sin(theta)
    ax = (c*xx+s*yy)/cover
    ay = (-s*xx+c*yy)/cover
    if p['flip']:
        ax = -ax
    ax += (aw-1)/2
    ay += (ah-1)/2
    valid = (ax >= 0) & (ay >= 0) & (ax <= aw-1) & (ay <= ah-1)
    rgb = cv.remap(asset, ax, ay, cv.INTER_LINEAR, borderMode=cv.BORDER_CONSTANT, borderValue=0)
    return np.ascontiguousarray(rgb), valid


def compose(pixels, sky, reflection, tint, masks, p, *, horizon_weight, align):
    """Float-in/float-out. Recovery mixes only this sky operator's contribution."""
    torch = optional_module('torch')
    from .matting import _lin_t, _slin_t
    original_dtype = pixels.dtype
    # FP32 has more mantissa than all RGB16 values; FP64 inputs stay FP64.
    dtype = torch.float64 if pixels.dtype == torch.float64 else torch.float32
    before = pixels.to(dtype)
    base = _lin_t(before.clamp(0, 1))
    alpha = align(masks['sky'].to(dtype)).clamp(0, 1)
    people = align(masks['person'].to(dtype)).clamp(0, 1)
    water = align(masks['water'].to(dtype)).clamp(0, 1) * horizon_weight
    recovery = align(masks['recovery'].to(dtype)).clamp(0, 1)
    # Explicit people always protect foreground details, even after edge expansion.
    alpha = alpha * (1-people) * (p['opacity']/100.)
    outside = (1-alpha)
    scene_strength = (p['scene']+100.)/200. * .24
    person_strength = (p['person']+100.)/200. * .16
    lighting = outside * ((1-people)*scene_strength + people*person_strength) * (p['opacity']/100.)
    # Match chromatic environment while preserving each pixel's linear luminance.
    target = base * tint
    weights = torch.as_tensor([.2126, .7152, .0722], dtype=dtype, device=base.device).reshape(1,3,1,1)
    light = (base*weights).sum(1, keepdim=True)
    target *= light / (target*weights).sum(1, keepdim=True).clamp_min(1e-8)
    harmonized = base + (target-base)*lighting
    out = harmonized*(1-alpha) + sky.to(dtype)*alpha
    reflection_alpha = water * (1-people) * (1-alpha) * (p['reflection']/100.) * (p['opacity']/100.)
    out = out*(1-reflection_alpha) + reflection.to(dtype)*reflection_alpha
    out = base + (out-base)*(1-recovery)
    encoded = _slin_t(out.clamp(0, 1)).to(original_dtype)
    # Exact neutral and fully recovered pixels preserve existing edit values.
    influence = (alpha + lighting + reflection_alpha)*(1-recovery)
    encoded = torch.where(influence > 0, encoded, pixels)
    if not torch.isfinite(encoded).all():
        raise ValueError('换天空输出包含非有限像素')
    return encoded
