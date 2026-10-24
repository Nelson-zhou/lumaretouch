# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact native field ABI. No implicit execution, build or Python fallback."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
from . import facial_sculpt_state as S
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)
MAX_PIXELS = 4_000_000
MAX_LOG_GAIN = .24


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_facial_sculpt.so'
    if not path.is_file():
        raise RuntimeError('Facial structure Rust kernel is not installed; no fallback')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_facial_sculpt_abi.argtypes = []
        lib.lrt_facial_sculpt_abi.restype = C.c_uint32
        if lib.lrt_facial_sculpt_abi() != 1:
            raise RuntimeError('Facial structure Rust ABI mismatch')
        lib.lrt_facial_sculpt_field_v1.argtypes = [P, C.c_size_t, P, C.c_size_t, P, C.c_size_t,
            C.c_size_t, C.c_size_t, C.c_float, C.c_float, C.c_size_t, P, C.c_size_t, CANCEL, C.c_void_p]
        lib.lrt_facial_sculpt_field_v1.restype = C.c_int
        return lib
    except (OSError, AttributeError) as error:
        raise RuntimeError('Facial structure native ABI could not load') from error


def available():
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def memory_estimate(shape):
    if (type(shape) not in (tuple, list) or len(shape) != 2
            or any(type(n) is not int or not 1 <= n <= 8192 for n in shape)
            or shape[0]*shape[1] > MAX_PIXELS):
        raise ValueError('Facial structure exceeds its exact-grid pixel limit')
    return shape[0]*shape[1]*64 + 16*1024*1024


def field(source, support, target, recipe, *, radius, cancelled=None):
    recipe = S.check(recipe)
    if type(radius) is not int or not 2 <= radius <= 128:
        raise ValueError('Facial structure radius must be a measured integer in [2,128]')
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    cancelled = cancelled or (lambda: False)
    def poll():
        if cancelled():
            raise InterruptedError('Facial structure cancelled; no field published')
    if type(source) is not np.ndarray or source.ndim != 3 or source.shape[-1] != 3:
        raise ValueError('Facial structure requires exact HWC RGB, not alpha')
    shape = source.shape[:2]
    from .cpu_memory_budget import available_estimate
    if memory_estimate(shape) > available_estimate():
        raise MemoryError('Facial structure independent snapshots exceed available memory')
    snapshots = []
    for array, expected in ((source, (*shape, 3)), (support, shape), (target, shape)):
        poll()
        if type(array) is not np.ndarray or array.dtype != np.float32 or array.shape != expected:
            raise ValueError('Facial structure arrays must be aligned native float32')
        value = np.array(array, dtype=np.float32, order='C', copy=True)
        if not np.isfinite(value).all() or np.any((value < 0) | (value > 1)):
            raise ValueError('Facial structure refuses nonfinite or non-SDR values; no clipping')
        value.setflags(write=False)
        snapshots.append(value)
    source, support, target = snapshots
    if np.any(target > support + 1e-6):
        raise ValueError('Facial target cannot exceed measured reviewed support')
    errors = []
    def callback(_):
        try:
            return int(bool(cancelled()))
        except BaseException as error:
            errors.append(error)
            return 1
    poll()
    cb = CANCEL(callback)
    output = np.empty(shape, np.float32)
    code = native().lrt_facial_sculpt_field_v1(source.ctypes.data_as(P), source.size,
        support.ctypes.data_as(P), support.size, target.ctypes.data_as(P), target.size,
        shape[1], shape[0], recipe['highlight'], recipe['shadow'], radius,
        output.ctypes.data_as(P), output.size, cb, None)
    if errors:
        raise errors[0]
    poll()
    if code == 4:
        raise InterruptedError('Facial structure native calculation cancelled')
    if code == 5:
        raise MemoryError('Facial structure native resource budget exceeded')
    if code:
        raise ValueError('Facial structure native refused, code ' + str(code))
    if (not np.isfinite(output).all() or np.any(np.abs(output) > MAX_LOG_GAIN + 1e-7)
            or np.any(output[target == 0] != 0)
            or (not recipe['highlight'] and np.any(output > 0))
            or (not recipe['shadow'] and np.any(output < 0))):
        raise ValueError('Facial structure returned an invalid signed support field')
    output.setflags(write=False)
    return output
