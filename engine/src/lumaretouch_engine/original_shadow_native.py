"""Length-explicit Rust uniform-floor shadow ABI. Source-only delivery, UNRUN.

No AI, runtime compilation, download, inpainting, clipping, or solver fallback.
Normal and Multiply are mathematically identical for this black scalar layer.
Soft Light is a distinct artistic darkening, not physical illumination recovery.
"""
import ctypes as C
from functools import lru_cache
import math
from pathlib import Path
import numpy as np

P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int)
ENCODING = 'linear-srgb-d65'
ESTIMATOR = 'uniform-diffuse-floor-scalar-v1'
MAX_PIXELS = 32_000_000
MAX_BYTES = 2_147_483_648
BLENDS = ('normal', 'multiply', 'softlight')


def available():
    return (Path(__file__).resolve().parent / 'bin/liblrt_original_shadow.so').is_file()


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_original_shadow.so'
    if not path.is_file():
        raise RuntimeError('原阴影 Rust 核心未安装；不会回退到 AI、源像素复制或代理导出')
    lib = C.CDLL(str(path))
    lib.lrt_original_shadow_abi.argtypes = []
    lib.lrt_original_shadow_abi.restype = C.c_uint32
    if lib.lrt_original_shadow_abi() != 1:
        raise RuntimeError('Original-shadow Rust ABI mismatch')
    lib.lrt_original_shadow_prepare.argtypes = [P, C.c_size_t] * 5 + [C.c_size_t, C.c_size_t, CANCEL]
    lib.lrt_original_shadow_prepare.restype = C.c_int
    lib.lrt_original_shadow_apply.argtypes = [P, C.c_size_t] * 3 + [C.c_size_t, C.c_size_t, C.c_float, C.c_uint32, CANCEL]
    lib.lrt_original_shadow_apply.restype = C.c_int
    return lib


def memory_estimate(shape):
    if not isinstance(shape, (tuple, list)) or len(shape) != 2:
        raise ValueError('Original-shadow preparation requires an HW shape')
    h, w = shape
    if (type(h) is not int or type(w) is not int or min(h, w) < 1
            or h * w > MAX_PIXELS or max(h, w) > 65536):
        raise ValueError('Original-shadow source dimensions exceed budget')
    # Inputs, contiguous copies, scalar and RGB outputs plus bounded row scratch.
    estimate = 64 * h * w + 67_108_864
    if estimate > MAX_BYTES:
        raise ValueError('Original-shadow full-source preparation exceeds 2GiB budget')
    return estimate


def _validate(array, shape, label, cancelled):
    if type(array) is not np.ndarray or array.dtype != np.float32 or array.shape != shape:
        raise ValueError('Original-shadow ' + label + ' must have matching float32 source-grid shape')
    for row in array:
        if cancelled():
            raise InterruptedError('Original-shadow preparation cancelled')
        if not np.isfinite(row).all() or np.any(row < 0) or np.any(row > 1):
            raise ValueError('Original-shadow requires finite SDR RGB and coverage in [0,1]; no clipping')


def _callback(cancelled):
    errors = []
    def poll():
        try:
            return int(bool(cancelled()))
        except BaseException as error:
            errors.append(error)
            return 1
    return CANCEL(poll), errors


def _result(code, cancelled, errors):
    if errors:
        raise errors[0]
    if code == 3 or cancelled():
        raise InterruptedError('Original-shadow preparation cancelled')
    if code == 4:
        raise MemoryError('Original-shadow full-source preparation exceeded admitted memory')
    messages = {1: 'invalid dimensions/settings', 2: 'non-finite or non-SDR input',
                5: 'insufficient reviewed lit-floor samples', 6: 'lit floor too dark for reliable extraction',
                7: 'nonuniform or incompatible floor samples; texture, reflections or different materials are unsupported'}
    if code:
        raise ValueError('Original-shadow extraction refused: ' + messages.get(code, 'unknown native error ' + str(code)))


def prepare(source_linear, alpha, lit_floor, retention, *, encoding=ENCODING, cancelled=lambda: False):
    if encoding != ENCODING or type(alpha) is not np.ndarray or alpha.ndim != 2:
        raise ValueError('Original-shadow requires explicit linear-sRGB-D65 RGB and reviewed HW alpha')
    shape = tuple(alpha.shape)
    memory_estimate(shape)
    for array, expected, label in ((source_linear, (*shape, 3), 'source RGB'),
                                   (alpha, shape, 'reviewed alpha'), (lit_floor, shape, 'lit floor'),
                                   (retention, shape, 'retention')):
        _validate(array, expected, label, cancelled)
    arrays = [np.ascontiguousarray(a) for a in (source_linear, alpha, lit_floor, retention)]
    output = np.empty(shape, np.float32)
    callback, errors = _callback(cancelled)
    args = [part for array in (*arrays, output) for part in (array.ctypes.data_as(P), array.size)]
    code = native().lrt_original_shadow_prepare(*args, shape[1], shape[0], callback)
    _result(code, cancelled, errors)
    _validate(output, shape, 'extracted opacity', cancelled)
    output.setflags(write=False)
    return output


def apply(background, shadow, *, strength=1., blend='normal', encoding=ENCODING, cancelled=lambda: False):
    if (encoding != ENCODING or blend not in BLENDS or isinstance(strength, bool)
            or not isinstance(strength, (int, float)) or not math.isfinite(strength) or not 0 <= strength <= 1
            or type(shadow) is not np.ndarray or shadow.ndim != 2):
        raise ValueError('Original-shadow application requires valid linear RGB, strength and blend')
    shape = tuple(shadow.shape)
    memory_estimate(shape)
    _validate(shadow, shape, 'extracted opacity', cancelled)
    _validate(background, (*shape, 3), 'replacement background', cancelled)
    bg, coverage = np.ascontiguousarray(background), np.ascontiguousarray(shadow)
    output = np.empty(background.shape, np.float32)
    callback, errors = _callback(cancelled)
    args = [part for array in (bg, coverage, output) for part in (array.ctypes.data_as(P), array.size)]
    code = native().lrt_original_shadow_apply(*args, shape[1], shape[0], strength, BLENDS.index(blend), callback)
    _result(code, cancelled, errors)
    _validate(output, (*shape, 3), 'shadowed background', cancelled)
    output.setflags(write=False)
    return output
