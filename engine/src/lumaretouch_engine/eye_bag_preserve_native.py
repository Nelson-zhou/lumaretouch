# SPDX-License-Identifier: GPL-3.0-or-later
"""Original Rust preservation-only ABI bridge. AUTHORED / UNRUN.

No runtime compiler, numerical fallback, inference or image resampling. The
caller separately authenticates source ownership and the existing bag solver.
"""
import ctypes as C
from functools import lru_cache
import math
from pathlib import Path
import numpy as np
from .cpu_memory_budget import available_estimate as _available_estimate

MAX_PIXELS = 32_000_000
MAX_DIMENSION = 65_536
SCRATCH_BYTES = 8 * 1024**2
# 28 B/px snapshots, 12 output, 12 native private staging. Caller adds 28 B/px.
ADDITIONAL_BYTES_PER_PIXEL = 52
TOTAL_BYTES_PER_PIXEL = 80
MAX_WORKING_BYTES = 3 * 1024**3
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_eye_bag_preserve.so'
    if not path.is_file():
        raise RuntimeError('Eye-bag preservation Rust core is not installed; no fallback applied')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_eye_bag_preserve_abi.argtypes = []
        lib.lrt_eye_bag_preserve_abi.restype = C.c_uint32
        if lib.lrt_eye_bag_preserve_abi() != 1:
            raise RuntimeError('Eye-bag preservation Rust ABI mismatch')
        lib.lrt_eye_bag_preserve_apply_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, P, C.c_size_t,
            C.c_size_t, C.c_size_t, C.c_float, P, C.c_size_t, CANCEL, C.c_void_p]
        lib.lrt_eye_bag_preserve_apply_v1.restype = C.c_int32
    except (OSError, AttributeError) as error:
        raise RuntimeError('Eye-bag preservation Rust core cannot load the required ABI') from error
    return lib


def available():
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def memory_estimate(shape):
    if (type(shape) not in (tuple, list) or len(shape) != 2
            or any(type(n) is not int or not 1 <= n <= MAX_DIMENSION for n in shape)):
        raise ValueError('Eye-bag preservation needs exact supported (height,width)')
    pixels = shape[0]*shape[1]
    if pixels > MAX_PIXELS or pixels*TOTAL_BYTES_PER_PIXEL+SCRATCH_BYTES > MAX_WORKING_BYTES:
        raise MemoryError('Eye-bag preservation exceeds native buffer admission; no proxy fallback')
    return pixels*ADDITIONAL_BYTES_PER_PIXEL+SCRATCH_BYTES


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Eye-bag preservation cancelled; private output discarded')


def _snapshot(value, shape, cancelled):
    if type(value) is not np.ndarray or value.dtype != np.float32 or value.shape != shape:
        raise ValueError('Eye-bag preservation requires exact float32 RGB/coverage shapes')
    _poll(cancelled)
    result = np.empty(shape, dtype=np.float32, order='C')
    for y in range(shape[0]):
        for x in range(0, shape[1], 4096):
            _poll(cancelled)
            block = result[y, x:x+4096]
            block[...] = value[y, x:x+4096]
            if not np.isfinite(block).all() or np.any((block < 0) | (block > 1)):
                raise ValueError('Eye-bag preservation refuses nonfinite/HDR RGB or invalid coverage')
    result.setflags(write=False)
    return result


def apply(source_rgb, corrected_rgb, protection, preserve, *, cancelled=None):
    """Return owned protected RGB, not a delta. All failures remain private.

    Strict opaque encoded-working-sRGB SDR only. Each input is independently
    snapshotted; caller must hold source and review immutable during that copy.
    Full preserve with exact coverage1 copies source bits, including signed0.
    Fractional coverage is encoded-space opacity, not physical relighting.
    """
    if type(preserve) not in (int, float) or not 0 <= preserve <= 1 or not math.isfinite(preserve):
        raise ValueError('Eye-bag preserve must be a finite number in [0,1]')
    if cancelled is None:
        cancelled = lambda: False
    if not callable(cancelled):
        raise TypeError('cancelled must be callable')
    if type(source_rgb) is not np.ndarray or source_rgb.ndim != 3 or source_rgb.shape[2] != 3:
        raise ValueError('Eye-bag preservation requires opaque HWC3 RGB; no alpha')
    h, w = source_rgb.shape[:2]
    extra = memory_estimate((h, w))
    _poll(cancelled)
    if extra > _available_estimate():
        raise MemoryError('Insufficient memory for preservation snapshots and native private output')
    source = _snapshot(source_rgb, (h, w, 3), cancelled)
    corrected = _snapshot(corrected_rgb, (h, w, 3), cancelled)
    coverage = _snapshot(protection, (h, w), cancelled)
    lib = native()
    output = np.empty((h, w, 3), dtype=np.float32, order='C')
    errors = []
    def poll(_context):
        if errors:
            return 1
        try:
            return int(bool(cancelled()))
        except BaseException as error:
            errors.append(error)
            return 1
    callback = CANCEL(poll)
    code = lib.lrt_eye_bag_preserve_apply_v1(
        source.ctypes.data_as(P), source.size,
        corrected.ctypes.data_as(P), corrected.size,
        coverage.ctypes.data_as(P), coverage.size,
        w, h, float(preserve), output.ctypes.data_as(P), output.size, callback, None)
    if errors:
        raise errors[0]
    if code == 4:
        raise InterruptedError('Eye-bag preservation cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Eye-bag preservation Rust resource admission refused')
    if code == 6:
        raise RuntimeError('Eye-bag preservation Rust panic contained; private output discarded')
    if code:
        labels = {1: 'ABI/lengths/dimensions/aliasing', 2: 'preserve setting', 3: 'pixel values or numerics'}
        raise ValueError('Eye-bag preservation Rust refused ' + labels.get(code, str(code)))
    output.setflags(write=False)
    return output
