"""Fixed-alpha Rust foreground/background estimation, then guarded colour despill.

Source-only delivery, UNRUN. No runtime compiler, download or alternative solver.
Caller authenticates immutable source RGB and reviewed foreground alpha. Fields
are a full render-domain preparation, not something an export tile may estimate.
Proxy preparation is independent and never certifies source-resolution export.
"""
import ctypes as C
from functools import lru_cache
import math
from pathlib import Path

import numpy as np

P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int)
MAX_PIXELS = 32_000_000
MAX_BYTES = 2_147_483_648
ENCODING = 'linear-srgb-d65'
ESTIMATOR = 'fixed-alpha-fb-edge-reflection-v1'
GAMUT_SAFETY = 1.0 - 2.0 ** -20


def available():
    return (Path(__file__).resolve().parent / 'bin/liblrt_spill_removal.so').is_file()


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_spill_removal.so'
    if not path.is_file():
        raise RuntimeError('背景溢色 Rust 核心未安装；不回退到全局去饱和、侵蚀或代理导出')
    lib = C.CDLL(str(path))
    lib.lrt_spill_removal_abi.argtypes = []
    lib.lrt_spill_removal_abi.restype = C.c_uint32
    if lib.lrt_spill_removal_abi() != 1:
        raise RuntimeError('Spill-removal Rust ABI mismatch')
    lib.lrt_spill_removal_prepare.argtypes = [P, P, P, P, C.c_size_t, C.c_size_t,
                                             C.c_float, C.c_float, CANCEL]
    lib.lrt_spill_removal_prepare.restype = C.c_int
    return lib


def _number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'Invalid spill-removal {label}')
    return float(value)


def memory_estimate(shape):
    """Conservative local peak bytes, not free space in the caller's pipeline.

    64*N + 64MiB includes original/copy RGB+alpha, output delta/confidence,
    seed maps, <=1024-side F/B, transient coarser fields, reduction and
    bounded validation/application row scratch. Max 32MP, max dimension 65536,
    admitted estimate <=2GiB. Caller must
    ADD its other retained ID-background/pipeline/tensor allocations before
    deciding whether the entire request fits its shared memory budget.
    """
    if not isinstance(shape, (tuple, list)) or len(shape) != 2:
        raise ValueError('Spill-removal requires an HW shape')
    h, w = shape
    if type(h) is not int or type(w) is not int or h <= 0 or w <= 0 or h * w > MAX_PIXELS or max(h, w) > 65536:
        raise ValueError('Spill-removal full-source dimensions exceed budget')
    estimate = 64 * h * w + 67_108_864
    if estimate > MAX_BYTES:
        raise ValueError('Spill-removal full-source preparation exceeds 2GiB budget')
    return estimate


def _validate_source(source, alpha, cancelled):
    if not isinstance(alpha, np.ndarray) or alpha.dtype != np.float32 or alpha.ndim != 2:
        raise ValueError('Spill removal requires reviewed HW float32 foreground alpha')
    if not isinstance(source, np.ndarray) or source.dtype != np.float32 or source.shape != (*alpha.shape, 3):
        raise ValueError('Spill removal requires matching HWC float32 immutable linear source RGB')
    memory_estimate(tuple(alpha.shape))
    for y in range(alpha.shape[0]):
        if cancelled():
            raise InterruptedError('Spill-removal preparation cancelled')
        if not np.isfinite(source[y]).all() or not np.isfinite(alpha[y]).all() or np.any((source[y] < 0) | (source[y] > 1)) or np.any((alpha[y] < 0) | (alpha[y] > 1)):
            raise ValueError('Spill-removal analysis requires finite SDR source RGB and alpha in [0,1]; no clipping')


def prepare(source_linear, alpha, *, strength=1.0, render_scale=1.0,
            encoding=ENCODING, cancelled=lambda: False):
    """Prepare full-domain raw delta and strength-weighted confidence ONCE.

    Actual correction is delta * confidence, not delta * confidence * strength.
    Estimate from ORIGINAL source, not current edits, replacement background,
    background-opacity weights or edge-adjusted composition alpha. Alpha is
    read-only. Full export uses original-size source/alpha, render_scale=1,
    prepares once and crops fields for tiles. Proxy fields cannot be upsampled
    to stand in for export. Identity/staleness/review receipts belong to caller.

    The fixed-alpha F/B estimate addresses mixed pixels. A separately gated
    near-edge interior-prior heuristic addresses some opaque reflected colour;
    deep opaque spill and real same-colour foreground remain ambiguous. This
    is not a learned matte or a guarantee of the original subject's true colour.
    The joint F/B pyramid is bounded to <=1024 on each axis, <=1,048,576 pixels.
    A full-source per-pixel refinement and gates use actual source RGB/alpha.
    This is coarse-guided colour estimation, not native-full-resolution F/B.
    """
    if encoding != ENCODING:
        raise ValueError('Spill removal requires explicit linear-sRGB-D65 source RGB')
    strength = _number(strength, 0, 1, 'strength')
    render_scale = _number(render_scale, 0.000001, 1, 'render scale')
    _validate_source(source_linear, alpha, cancelled)
    delta = np.zeros(source_linear.shape, dtype=np.float32)
    confidence = np.zeros(alpha.shape, dtype=np.float32)
    fields = {'delta': delta, 'confidence': confidence, 'encoding': encoding,
              'render_scale': render_scale, 'domain_shape': tuple(alpha.shape),
              'estimator': ESTIMATOR}
    if strength == 0:
        delta.flags.writeable = False
        confidence.flags.writeable = False
        return fields
    source = np.ascontiguousarray(source_linear)
    matte = np.ascontiguousarray(alpha)
    errors = []

    def poll():
        try:
            return int(bool(cancelled()))
        except BaseException as error:
            errors.append(error)
            return 1

    callback = CANCEL(poll)
    h, w = alpha.shape
    code = native().lrt_spill_removal_prepare(source.ctypes.data_as(P), matte.ctypes.data_as(P),
        delta.ctypes.data_as(P), confidence.ctypes.data_as(P), w, h, strength, render_scale, callback)
    if errors:
        raise errors[0]
    if code == 3 or cancelled():
        raise InterruptedError('Spill-removal preparation cancelled')
    if code == 4:
        raise MemoryError('Spill-removal full-source preparation exceeded admitted memory')
    if code:
        raise ValueError(f'Spill-removal Rust preparation rejected input/numerics: {code}')
    # Failed/cancelled scratch never escapes. These arrays are immutable until
    # caller explicitly copies confidence to multiply reviewed edit coverage.
    delta.flags.writeable = False
    confidence.flags.writeable = False
    return fields


def apply_fields(current_linear, fields, *, cancelled=lambda: False):
    """Apply prepared correction to CURRENT linear RGB with row-bounded scratch.

    d = delta * confidence. For each SDR pixel, k = min(1,
    (1-Cc)/dc for dc>0, -Cc/dc for dc<0), across all three channels. If k<1,
    multiply k by (1-2^-20) before C+d*k. One common scale preserves the
    luminance-null direction. No componentwise RGB clipping or desaturation.
    Finite edited HDR pixels outside [0,1] remain exact, not forced into SDR.
    Neutral confidence/delta pixels remain bit-exact; non-finite RGB is refused.
    A cropped field is accepted only with matching current/domain_shape.
    """
    if not isinstance(fields, dict) or fields.get('encoding') != ENCODING:
        raise ValueError('Spill-removal fields use an unsupported RGB encoding')
    if fields.get('estimator') != ESTIMATOR:
        raise ValueError('Spill-removal fields use an unsupported estimator version')
    _number(fields.get('render_scale'), 0.000001, 1, 'field render scale')
    delta, confidence = fields.get('delta'), fields.get('confidence')
    if not isinstance(confidence, np.ndarray) or confidence.dtype != np.float32 or confidence.ndim != 2 or not isinstance(delta, np.ndarray) or delta.dtype != np.float32 or delta.shape != (*confidence.shape, 3):
        raise ValueError('Spill-removal delta/confidence field mismatch')
    domain_shape = fields.get('domain_shape')
    if not isinstance(domain_shape, (tuple, list)) or tuple(domain_shape) != tuple(confidence.shape):
        raise ValueError('Spill-removal field-domain metadata mismatch')
    memory_estimate(tuple(confidence.shape))
    if not isinstance(current_linear, np.ndarray) or current_linear.dtype != np.float32 or current_linear.shape != delta.shape:
        raise ValueError('Spill-removal current RGB/field shape mismatch')
    result = np.empty_like(current_linear)
    for y in range(confidence.shape[0]):
        if cancelled():
            raise InterruptedError('Spill-removal application cancelled')
        current = current_linear[y]
        q = confidence[y]
        raw = delta[y]
        if not np.isfinite(current).all() or not np.isfinite(q).all() or not np.isfinite(raw).all() or np.any((q < 0) | (q > 1)):
            raise ValueError('Spill-removal current RGB/fields must be finite with confidence in [0,1]')
        result[y] = current
        active = (q > 0) & np.any(raw != 0, axis=1) & np.all((current >= 0) & (current <= 1), axis=1)
        if not np.any(active):
            continue
        c = current.astype(np.float64)
        d = raw.astype(np.float64) * q.astype(np.float64)[:, None]
        room = np.full(d.shape, np.inf, dtype=np.float64)
        np.divide(1.0 - c, d, out=room, where=d > 0)
        np.divide(-c, d, out=room, where=d < 0)
        k = np.minimum(1.0, np.min(room, axis=1))
        k = np.where(k < 1.0, np.maximum(k, 0.0) * GAMUT_SAFETY, k)
        candidate = c + d * k[:, None]
        if not np.isfinite(candidate[active]).all() or np.any((candidate[active] < 0) | (candidate[active] > 1)):
            raise ValueError('Spill-removal gamut line step failed; no clipping fallback')
        result[y, active] = candidate[active].astype(np.float32)
    return result
