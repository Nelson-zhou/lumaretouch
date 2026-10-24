# SPDX-License-Identifier: GPL-3.0-or-later
"""Original same-face source-owned chromatic evenness ABI. AUTHORED / UNRUN.

prepare measures immutable own-source log chroma, never current edited pixels.
apply preserves each ACTUAL current-stage pixel's linear luminance. HWC2 is a
bounded log-ratio displacement, not RGB, a target palette or an encoded delta.
No Python algorithm fallback, runtime build, external download or RGB8 path.
"""
import ctypes as C
from functools import lru_cache
import math
from pathlib import Path

import numpy as np

from .cpu_memory_budget import available_estimate as _available_estimate

MAX_PIXELS = 32_000_000
MAX_DIMENSION = 65_536
MIN_RADIUS = 4
MAX_RADIUS = 256
MIN_REFERENCE_SAMPLES = 64
MAX_SHIFT = 0.09
SHIFT_TOLERANCE = 1e-7
LUMINANCE_TOLERANCE = 2e-7
NATIVE_SCRATCH_BYTES_PER_PIXEL = 88
NATIVE_TOTAL_BYTES_PER_PIXEL = 112
ADDITIONAL_BYTES_PER_PIXEL = 112
TOTAL_BYTES_PER_PIXEL = 128
APPLY_ADDITIONAL_BYTES_PER_PIXEL = 44
APPLY_TOTAL_BYTES_PER_PIXEL = 64
MAX_WORKING_BYTES = 4 * 1024**3
SCRATCH_BYTES = 8 * 1024**2
COPY_PIXELS = 4096
ENCODING = 'encoded-working-srgb-d65-sdr'
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_skin_evenness.so'
    if not path.is_file():
        raise RuntimeError('Skin evenness Rust core is not installed; no fallback was applied')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_skin_evenness_abi.argtypes = []
        lib.lrt_skin_evenness_abi.restype = C.c_uint32
        if lib.lrt_skin_evenness_abi() != 1:
            raise RuntimeError('Skin evenness Rust ABI mismatch')
        lib.lrt_skin_evenness_prepare_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t,
            C.c_float, C.c_size_t, P, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_skin_evenness_prepare_v1.restype = C.c_int
        lib.lrt_skin_evenness_apply_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t,
            P, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_skin_evenness_apply_v1.restype = C.c_int
    except (OSError, AttributeError) as error:
        raise RuntimeError('Skin evenness Rust core cannot load its required ABI') from error
    return lib


def available():
    """Required symbol/ABI loading only, never a claim of image acceptance."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def _estimate(shape, additional_bytes, total_bytes):
    if type(shape) not in (tuple, list) or len(shape) != 2:
        raise ValueError('Skin evenness memory estimate requires exact (height,width)')
    height, width = shape
    if (type(width) is not int or type(height) is not int
            or min(width, height) < 1 or max(width, height) > MAX_DIMENSION):
        raise ValueError('Skin evenness dimensions are outside the supported range')
    pixels = width * height
    if pixels > MAX_PIXELS or total_bytes * pixels + SCRATCH_BYTES > MAX_WORKING_BYTES:
        raise MemoryError('Skin evenness exceeds its memory/pixel budget; no proxy fallback')
    return additional_bytes * pixels + SCRATCH_BYTES


def memory_estimate(shape):
    """Pure prepare additional estimate: snapshots16 + output8 + native88 B/px.

    Add 8MiB validation/allocator allowance. Caller source/coverage add16 B/px.
    No native load, image allocation or live memory probe. Not measured peak,
    guaranteed process memory or latency; host admits combined renderer resources.
    """
    return _estimate(shape, ADDITIONAL_BYTES_PER_PIXEL, TOTAL_BYTES_PER_PIXEL)


def application_memory_estimate(shape):
    """Pure apply estimate: snapshots20 + output12 + private native12 B/px.

    Caller current RGB/shift add20 B/px. Also includes 8MiB bounded allowance.
    """
    return _estimate(shape, APPLY_ADDITIONAL_BYTES_PER_PIXEL, APPLY_TOTAL_BYTES_PER_PIXEL)


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Skin evenness cancelled; private output discarded')


def _control(value):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError('Skin evenness amount requires a finite number in [0,1]')
    try:
        amount = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError('Skin evenness amount requires a finite number in [0,1]') from error
    if not math.isfinite(amount) or not 0 <= amount <= 1:
        raise ValueError('Skin evenness amount requires a finite number in [0,1]')
    return amount


def _shape(array, shape, label):
    if type(array) is not np.ndarray or array.dtype != np.float32 or array.shape != shape:
        raise ValueError(label + ' requires exact native float32 shape ' + str(shape))


def _rgb_shape(array, label):
    if type(array) is not np.ndarray or array.ndim != 3 or array.shape[2] != 3:
        raise ValueError(label + ' requires an HWC float32 RGB array')
    _shape(array, array.shape, label)
    return array.shape[:2]


def _blocks(shape):
    for row in range(shape[0]):
        for left in range(0, shape[1], COPY_PIXELS):
            yield row, slice(left, min(left + COPY_PIXELS, shape[1]))


def _valid_shift(block):
    if not np.isfinite(block).all():
        return False
    values = block.astype(np.float64)
    return bool(np.all(np.hypot(values[..., 0], values[..., 1]) <= MAX_SHIFT + SHIFT_TOLERANCE))


def _snapshot(array, shape, label, cancelled, *, shift=False):
    _shape(array, shape, label)
    _poll(cancelled)
    result = np.empty(shape, dtype=np.float32, order='C')
    for row, columns in _blocks(shape):
        _poll(cancelled)
        block = result[row, columns]
        block[...] = array[row, columns]
        if shift:
            if not _valid_shift(block):
                raise ValueError(label + ' requires finite HWC2 log-chroma vectors with norm <=0.09')
        elif not np.isfinite(block).all() or np.any(block < 0.0) or np.any(block > 1.0):
            raise ValueError(label + ' requires finite SDR [0,1] values; no clipping')
    result.setflags(write=False)
    _poll(cancelled)
    return result


def _callback(cancelled):
    errors = []
    def poll(_context):
        if errors:
            return 1
        try:
            return int(bool(cancelled()))
        except BaseException as error:
            errors.append(error)
            return 1
    return CANCEL(poll), errors


def _result(code, cancelled, errors):
    if errors:
        raise errors[0]
    if code == 4:
        raise InterruptedError('Skin evenness cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Skin evenness Rust resource budget exceeded')
    if code == 6:
        raise RuntimeError('Skin evenness Rust panic contained; private output discarded')
    if code:
        messages = {1: 'invalid ABI, lengths, dimensions or buffer aliasing',
                    2: 'invalid amount or measured face-scale radius',
                    3: 'nonfinite, non-SDR RGB/coverage, unbounded shift or numerical refusal',
                    7: 'insufficient reliable own-face source reference (at least 64 samples required)',
                    8: 'insufficient supported source guided context'}
        raise ValueError('Skin evenness Rust refused: ' + messages.get(code, str(code)))


def _admit(shape, cancelled, *, application=False):
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    _poll(cancelled)
    estimate = application_memory_estimate(shape) if application else memory_estimate(shape)
    if estimate > _available_estimate():
        raise MemoryError('Insufficient CPU memory for independent skin evenness snapshots and native scratch')


def prepare(source_rgb, coverage, amount, *, radius, cancelled=lambda: False):
    """Return owned read-only float32 HWC2 source-measured log(R/G),log(B/G) shift.

    Source is the original immutable effective source, not an edited stage.
    Host authenticates source/revision/person/geometry, actual measured face skin,
    exclusions and source-grid scale. A rectangle alone grants no permission.
    Evaluate the complete own-face support plus real 2*radius halo (or full
    source); global reference requires EVERY own-face permitted source sample.
    An arbitrary tile plus halo is not equivalent. No per-tile reference solve.

    radius is strict int4..256. All input is validated even at amount zero.
    Zero amount yields exact zero shift. Active preparation requires >=64 actual
    own-source samples with coverage*photometric_reliability>=.75, and at least
    one adequate guided neighborhood; otherwise explicit refusal, not fake neutral
    success. Invalid local neighborhoods yield zero. Field norm<=.09(+roundoff).
    No measured luminance is replaced or carried as an RGB placeholder.
    """
    amount = _control(amount)
    if type(radius) is not int or not MIN_RADIUS <= radius <= MAX_RADIUS:
        raise ValueError('Skin evenness radius requires an integer in [4,256] from measured face scale')
    height, width = _rgb_shape(source_rgb, 'Original source RGB')
    _shape(coverage, (height, width), 'Face skin coverage')
    _admit((height, width), cancelled)
    source = _snapshot(source_rgb, source_rgb.shape, 'Original source RGB', cancelled)
    weight = _snapshot(coverage, coverage.shape, 'Face skin coverage', cancelled)
    _poll(cancelled)
    lib = native()
    _poll(cancelled)
    output = np.empty((height, width, 2), dtype=np.float32, order='C')
    callback, errors = _callback(cancelled)
    code = lib.lrt_skin_evenness_prepare_v1(
        source.ctypes.data_as(P), source.size, weight.ctypes.data_as(P), weight.size,
        width, height, amount, radius, output.ctypes.data_as(P), output.size, callback, None,
    )
    _result(code, cancelled, errors)
    for row, columns in _blocks(output.shape):
        _poll(cancelled)
        block = output[row, columns]
        if not _valid_shift(block):
            raise RuntimeError('Skin evenness returned invalid or unbounded log-chroma field; discarded')
        protected = weight[row, columns] == 0.0
        if amount == 0.0:
            protected = np.ones_like(protected, dtype=bool)
        if np.any(block[protected] != 0.0):
            raise RuntimeError('Skin evenness returned nonzero neutral or unsupported shift; discarded')
    _poll(cancelled)
    output.setflags(write=False)
    return output


def _luminance(encoded):
    values = encoded.astype(np.float64)
    linear = np.where(values <= 0.04045, values / 12.92,
                      ((values + 0.055) / 1.055)**2.4)
    return linear[..., 0]*0.2126 + linear[..., 1]*0.7152 + linear[..., 2]*0.0722


def apply(current_rgb, shift, *, cancelled=lambda: False):
    """Apply bounded source shift to actual current RGB at its original linear Y.

    Linear channels multiply by [exp(du),1,exp(dv)], then common renormalization
    restores that CURRENT pixel's Y. One feasible interpolation current->proposal
    maintains gamut and Y together. Never independent-channel clipping. Preserved
    Y is a numerical invariant, not a guarantee of unchanged perceived brightness.
    Zero shift/pure black/pure white are exact bit copies. No source statistics
    are recomputed on tiles or changed current RGB; caller owns field provenance.
    Strict float32 finite SDR HWC3 and finite bounded HWC2; independent immutable
    snapshots admit strides, not mutation during snapshot. New owned result only.
    Missing core refuses even neutral calls. No partial publication or fallback.
    """
    height, width = _rgb_shape(current_rgb, 'Current RGB')
    _shape(shift, (height, width, 2), 'Log-chroma shift')
    _admit((height, width), cancelled, application=True)
    current = _snapshot(current_rgb, current_rgb.shape, 'Current RGB', cancelled)
    field = _snapshot(shift, shift.shape, 'Log-chroma shift', cancelled, shift=True)
    _poll(cancelled)
    lib = native()
    _poll(cancelled)
    output = np.empty_like(current, order='C')
    callback, errors = _callback(cancelled)
    code = lib.lrt_skin_evenness_apply_v1(
        current.ctypes.data_as(P), current.size, field.ctypes.data_as(P), field.size,
        width, height, output.ctypes.data_as(P), output.size, callback, None,
    )
    _result(code, cancelled, errors)
    for row, columns in _blocks(output.shape):
        _poll(cancelled)
        block, original = output[row, columns], current[row, columns]
        if not np.isfinite(block).all() or np.any(block < 0.0) or np.any(block > 1.0):
            raise RuntimeError('Skin evenness returned invalid SDR output; discarded')
        protected = (np.all(field[row, columns] == 0.0, axis=-1)
                     | np.all(original == 0.0, axis=-1) | np.all(original == 1.0, axis=-1))
        if not np.array_equal(block[protected].view(np.uint32), original[protected].view(np.uint32)):
            raise RuntimeError('Skin evenness changed neutral or endpoint pixels; discarded')
        if np.any(np.abs(_luminance(block) - _luminance(original)) > LUMINANCE_TOLERANCE):
            raise RuntimeError('Skin evenness changed current linear luminance; discarded')
    _poll(cancelled)
    return output
