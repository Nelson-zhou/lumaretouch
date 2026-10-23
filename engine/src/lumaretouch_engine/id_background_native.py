"""Explicit linear-sRGB, full-support Rust fields; no model or runtime build fallback.

Callers must authenticate reviewed source-domain alpha before this numerical layer.
Proxy render_scale is explicit and never authorizes upsampling a proxy for export.
Fields are composited with CURRENT pipeline RGB, never a cached original photograph.
"""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import math
import numpy as np

P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int)
MAX_PIXELS = 32_000_000


def available():
    return (Path(__file__).resolve().parent / 'bin/liblrt_id_background.so').is_file()


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_id_background.so'
    if not path.is_file():
        raise RuntimeError('证件照背景 Rust 核心未安装；不回退到代理蒙版或其他算法')
    lib = C.CDLL(str(path))
    lib.lrt_id_background_abi.argtypes = []
    lib.lrt_id_background_abi.restype = C.c_uint32
    if lib.lrt_id_background_abi() != 1:
        raise RuntimeError('ID-background Rust ABI mismatch')
    lib.lrt_id_background_prepare.argtypes = [P, P, P, P, C.c_size_t, C.c_size_t, P, C.c_uint32, C.c_uint32, CANCEL]
    lib.lrt_id_background_prepare.restype = C.c_int
    return lib


def _number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'Invalid ID-background {label}')
    return float(value)


def _params(recipe, render_scale):
    scale = _number(render_scale, 0.000001, 1, 'render scale')
    shadow = recipe.get('shadow') or {}
    kind = shadow.get('kind', 'none')
    blend = shadow.get('blend', 'normal')
    if kind not in ('none', 'soft', 'hard', 'silhouette') or blend not in ('normal', 'multiply', 'softlight'):
        raise ValueError('Unsupported ID-background shadow kind/blend')
    color = shadow.get('color', [0, 0, 0])
    if not isinstance(color, (list, tuple)) or len(color) != 3:
        raise ValueError('Shadow color must be sRGB RGB8')
    rgb = [_number(v, 0, 255, 'shadow RGB') / 255 for v in color]
    # CSS/W3C soft-light formula is deliberately evaluated in linear sRGB here.
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    p = [_number(recipe.get('edge', 0), -20, 20, 'edge') * scale,
         _number(recipe.get('opacity', 1), 0, 1, 'background opacity'),
         _number(shadow.get('opacity', 0), 0, 1, 'shadow opacity'),
         _number(shadow.get('blur', 0), 0, 256, 'shadow blur') * scale,
         _number(shadow.get('gradient', 0), 0, 1, 'shadow gradient'),
         _number(shadow.get('x', 0), -65536, 65536, 'shadow x') * scale,
         _number(shadow.get('y', 0), -65536, 65536, 'shadow y') * scale,
         _number(shadow.get('distance', 0), 0, 65536, 'shadow distance') * scale,
         _number(shadow.get('angle', 0), -360, 360, 'shadow angle'), *linear]
    return np.asarray(p, dtype=np.float32), ('none', 'soft', 'hard', 'silhouette').index(kind), ('normal', 'multiply', 'softlight').index(blend)


def memory_estimate(shape, recipe, *, render_scale=1):
    """Conservative bytes incl. input/copies/output and full shadow halo.

    Does not include other current-pipeline allocations held by the caller.
    """
    h, w = shape
    if type(h) is not int or type(w) is not int or not 0 < h * w <= MAX_PIXELS or max(h, w) > 65536:
        raise ValueError('ID-background full-support dimensions exceed budget')
    params, kind, _ = _params(recipe, render_scale)
    radius = math.floor(float(params[3]) + 0.5) if kind and params[2] > 0 else 0
    support = (w + 2 * radius) * (h + 2 * radius)
    estimate = 52 * h * w + 8 * support
    if support > 64_000_000 or estimate > 2_147_483_648:
        raise ValueError('ID-background full-support shadow halo exceeds 2GiB budget')
    return estimate


def prepare(alpha, background, recipe, *, render_scale=1, encoding='linear-srgb-d65', cancelled=lambda: False):
    """Return {alpha: foreground weight, background: shadowed linear RGB}.

    Whole render-domain arrays are mandatory. Full export supplies original-size
    reviewed alpha and render_scale=1, then crops these fields for export tiles.
    Edge is separable square dilation/erosion rounded to render pixels. Blur is
    a finite-support separable box blur, not a learned or Gaussian hair matte.
    Memory cap: 32MP source, 64MP shadow halo, estimated <=2GiB total.
    Estimate is 52*source_pixels + 8*halo_pixels, including caller inputs,
    optional contiguous copies, native scratch and output fields. The halo
    extends by the source-scaled blur radius on every side. Callers must also
    admit their other pipeline allocations; use memory_estimate for the bound.
    """
    if encoding != 'linear-srgb-d65':
        raise ValueError('ID background requires explicit linear-sRGB-D65 background RGB')
    if not isinstance(alpha, np.ndarray) or alpha.dtype != np.float32 or alpha.ndim != 2:
        raise ValueError('ID background requires source-reviewed HW float32 alpha')
    if not isinstance(background, np.ndarray) or background.dtype != np.float32 or background.shape != (*alpha.shape, 3):
        raise ValueError('ID background requires matching HWC float32 linear RGB')
    h, w = alpha.shape
    if not 0 < h * w <= MAX_PIXELS or max(h, w) > 65536:
        raise ValueError('ID-background full-support 32MP memory budget exceeded')
    params, kind, blend = _params(recipe, render_scale)
    memory_estimate((h, w), recipe, render_scale=render_scale)
    if cancelled():
        raise InterruptedError('ID background cancelled')
    # Even neutral fields retain shape/recipe validation; no native dependency needed.
    if params[1] == 0:
        return {'alpha': np.ones(alpha.shape, dtype=np.float32), 'background': background,
                'encoding': encoding, 'render_scale': float(render_scale)}
    matte = np.ascontiguousarray(alpha)
    bg = np.ascontiguousarray(background)
    output = np.empty(background.shape, dtype=np.float32)
    weight = np.empty(alpha.shape, dtype=np.float32)
    errors = []
    def poll():
        try:
            return int(bool(cancelled()))
        except BaseException as error:
            errors.append(error)
            return 1
    callback = CANCEL(poll)
    code = native().lrt_id_background_prepare(bg.ctypes.data_as(P), matte.ctypes.data_as(P),
        output.ctypes.data_as(P), weight.ctypes.data_as(P), w, h, params.ctypes.data_as(P), kind, blend, callback)
    if errors:
        raise errors[0]
    if code == 3 or cancelled():
        raise InterruptedError('ID background cancelled')
    if code:
        raise ValueError(f'ID-background Rust preparation rejected input/budget: {code}')
    return {'alpha': weight, 'background': output, 'encoding': encoding, 'render_scale': float(render_scale)}


def apply_fields(source, fields, *, cancelled=lambda: False):
    """Convenience CPU compositor of current linear RGB, bounded row scratch."""
    if fields.get('encoding') != 'linear-srgb-d65':
        raise ValueError('ID-background fields use an unsupported RGB encoding')
    alpha, background = fields['alpha'], fields['background']
    if not isinstance(source, np.ndarray) or source.dtype != np.float32 or source.shape != background.shape or source.shape != (*alpha.shape, 3):
        raise ValueError('ID-background current RGB/field shape mismatch')
    result = np.empty_like(source)
    for y in range(len(source)):
        if cancelled():
            raise InterruptedError('ID background cancelled')
        # weighted difference gives bit-exact neutral bypass, including alpha=1.
        result[y] = source[y] + (1 - alpha[y, :, None]) * (background[y] - source[y])
    return result


def apply(source, background, alpha, recipe, *, encoding='linear-srgb-d65', render_scale=1, cancelled=lambda: False):
    if encoding != 'linear-srgb-d65':
        raise ValueError('ID background requires current linear-sRGB-D65 RGB')
    params, _, _ = _params(recipe, render_scale)
    if params[1] == 0:
        return source
    return apply_fields(source, prepare(alpha, background, recipe, encoding=encoding,
        render_scale=render_scale, cancelled=cancelled), cancelled=cancelled)
