# SPDX-License-Identifier: GPL-3.0-or-later
"""Original source-measured dark lip-furrow Rust boundary. AUTHORED / UNRUN.

No Python image algorithm fallback, runtime build, download or source resampling.
Every array is snapshotted independently before the native call. Photographic
eligibility and evidence provenance are the host's responsibility, not the ABI's.
"""
import ctypes as C
from functools import lru_cache
import math
from pathlib import Path

import numpy as np

from .cpu_memory_budget import available_estimate as _available_estimate

MAX_PIXELS = 32_000_000
MAX_DIMENSION = 65_536
MIN_RADIUS = 1
MAX_RADIUS = 12
FULL_SUPPORT = 0.999
SUPPORT_GUARD_MULTIPLIER = 3
NATIVE_SCRATCH_BYTES_PER_PIXEL = 28
NATIVE_TOTAL_BYTES_PER_PIXEL = 56
ADDITIONAL_BYTES_PER_PIXEL = 56
TOTAL_BYTES_PER_PIXEL = 72
MAX_WORKING_BYTES = 4 * 1024**3
SCRATCH_BYTES = 8 * 1024**2
COPY_PIXELS = 4096
ENCODING = 'encoded-working-srgb-d65-sdr'
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_lip_texture.so'
    if not path.is_file():
        raise RuntimeError('Lip texture Rust core is not installed; no fallback was applied')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_lip_texture_abi.argtypes = []
        lib.lrt_lip_texture_abi.restype = C.c_uint32
        if lib.lrt_lip_texture_abi() != 1:
            raise RuntimeError('Lip texture Rust ABI mismatch')
        lib.lrt_lip_texture_apply_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t,
            C.c_float, C.c_float, C.c_float, C.c_size_t,
            P, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_lip_texture_apply_v1.restype = C.c_int
    except (OSError, AttributeError) as error:
        raise RuntimeError('Lip texture Rust core cannot load its required ABI') from error
    return lib


def available():
    """Only required symbol/ABI loading; no claim of mouth/source eligibility."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def memory_estimate(shape):
    """Pure additional bytes for exact (height,width), no native/live read.

    16 B/px independent source/coverage snapshots + 12 B/px Python-owned output
    + 28 B/px native linear image/private commit image/support prefix, plus 8 MiB
    for the prefix extra row/column, bounded validation and allocator allowance.
    Caller-owned RGB/coverage add 16 B/px to the admitted 72 B/px total. Host
    must separately admit anatomy, document intermediates and any other owners.
    This estimate is not an allocation success/OOM guarantee.
    """
    if type(shape) not in (tuple, list) or len(shape) != 2:
        raise ValueError('Lip texture memory estimate requires exact (height,width)')
    height, width = shape
    if (type(width) is not int or type(height) is not int
            or min(width, height) < 1 or max(width, height) > MAX_DIMENSION):
        raise ValueError('Lip texture dimensions are outside the supported range')
    pixels = width * height
    if (pixels > MAX_PIXELS
            or TOTAL_BYTES_PER_PIXEL * pixels + SCRATCH_BYTES > MAX_WORKING_BYTES):
        raise MemoryError('Lip texture exceeds its memory/pixel budget; no proxy fallback')
    return ADDITIONAL_BYTES_PER_PIXEL * pixels + SCRATCH_BYTES


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Lip texture cancelled; private output discarded')


def _number(value, label):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError(label + ' requires a finite number')
    try:
        value = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(label + ' requires a finite number') from error
    if not math.isfinite(value):
        raise ValueError(label + ' requires a finite number')
    return value


def _axis(value):
    if type(value) not in (tuple, list) or len(value) != 2:
        raise ValueError('Lip texture across requires two measured unit-axis coordinates')
    x, y = (_number(v, 'Lip texture across') for v in value)
    if abs(math.hypot(x, y) - 1.0) > 0.0001:
        raise ValueError('Lip texture across must already be a measured unit axis')
    return x, y


def _shape(array, shape, label):
    if type(array) is not np.ndarray or array.dtype != np.float32 or array.shape != shape:
        raise ValueError(label + ' requires exact native float32 shape ' + str(shape))


def _blocks(shape):
    for row in range(shape[0]):
        for left in range(0, shape[1], COPY_PIXELS):
            yield row, slice(left, min(left + COPY_PIXELS, shape[1]))


def _snapshot(array, shape, label, cancelled):
    _shape(array, shape, label)
    _poll(cancelled)
    snapshot = np.empty(shape, dtype=np.float32, order='C')
    for row, columns in _blocks(shape):
        _poll(cancelled)
        block = snapshot[row, columns]
        block[...] = array[row, columns]
        if not np.isfinite(block).all() or np.any(block < 0.0) or np.any(block > 1.0):
            raise ValueError(label + ' requires finite SDR [0,1] values; no clipping')
    snapshot.setflags(write=False)
    _poll(cancelled)
    return snapshot


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
        raise InterruptedError('Lip texture cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Lip texture Rust resource budget exceeded')
    if code == 6:
        raise RuntimeError('Lip texture Rust panic contained; private output discarded')
    if code:
        messages = {1: 'invalid ABI, lengths, dimensions or buffer aliasing',
                    2: 'invalid amount, measured axis or measured radius',
                    3: 'nonfinite/non-SDR RGB or coverage, or numerical refusal'}
        raise ValueError('Lip texture Rust refused: ' + messages.get(code, str(code)))


def apply(source_rgb, coverage, amount, *, across, radius, cancelled=lambda: False):
    """Return owned float32 encoded working-sRGB-D65 SDR RGB on the source grid.

    source_rgb is the ORIGINAL effective source, never a previous texture result
    or lipstick/lip-makeup intermediate. coverage is true measured permission
    on separate upper/lower lip surfaces, with cavity/seam, corners, other people
    and known occluders excluded. It is not a guessed rectangle or a semantic
    confidence score. The host authenticates source/revision/face/transform and
    reports insufficient complete footprints distinctly from no dark furrows.

    across is a measured unit mouth-corner axis, not a portable recipe option;
    radius is an exact Python int 1..12 measured from current-grid mouth/surface
    scale. Full-source evaluation is preferred. A cropped evaluation needs a
    real 3*radius+1-pixel halo with original RGB/coverage; never invent a halo,
    clamp samples, downsample, or alter radius to disguise resource refusal.

    Every candidate needs an entirely supported square of radius 3*radius with
    coverage>=0.999. Five paired-flank cross-sections at measured axis and +/-30
    degrees reject edges, short blobs, bright flakes and deep/clipped shadows.
    One common multiplicative linear-RGB gain raises luminance by at most 35% of
    the measured supported dark residual while preserving source channel ratios.
    This is conservative appearance attenuation, not semantic repair,
    reconstruction, dry-flake treatment, medical diagnosis or validated quality.

    Zero amount and unsupported pixels are exact bit copies, including -0.0.
    All inputs must be finite [0,1] even when neutral. Exact native float32 RGB
    HWC/HW only; RGB16 must be converted without truncating its low bits before
    this boundary. Alpha, HDR, implicit transfer/profile conversion, tensors and
    retained/aliased snapshots are refused. Strided arrays are independently
    copied. Caller must keep inputs immutable while snapshotting. No partial
    output is published on cancellation/errors; no runtime build or fallback.
    """
    amount = _number(amount, 'Lip texture amount')
    if not 0.0 <= amount <= 1.0:
        raise ValueError('Lip texture amount must be in [0,1]')
    axis = _axis(across)
    if type(radius) is not int or not MIN_RADIUS <= radius <= MAX_RADIUS:
        raise ValueError('Lip texture radius requires an integer in [1,12] from measured mouth scale')
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    if type(source_rgb) is not np.ndarray or source_rgb.ndim != 3 or source_rgb.shape[2] != 3:
        raise ValueError('Lip texture requires an HWC float32 RGB array, no alpha')
    height, width, _ = source_rgb.shape
    _shape(source_rgb, (height, width, 3), 'Source RGB')
    _shape(coverage, (height, width), 'Lip permission coverage')
    _poll(cancelled)
    additional = memory_estimate((height, width))
    if additional > _available_estimate():
        raise MemoryError('Insufficient CPU memory for independent lip texture snapshots and native scratch')
    source = _snapshot(source_rgb, source_rgb.shape, 'Source RGB', cancelled)
    weight = _snapshot(coverage, coverage.shape, 'Lip permission coverage', cancelled)
    _poll(cancelled)
    lib = native()
    _poll(cancelled)
    output = np.empty_like(source, order='C')
    callback, errors = _callback(cancelled)
    code = lib.lrt_lip_texture_apply_v1(
        source.ctypes.data_as(P), source.size, weight.ctypes.data_as(P), weight.size,
        width, height, amount, axis[0], axis[1], radius,
        output.ctypes.data_as(P), output.size, callback, None,
    )
    _result(code, cancelled, errors)
    for row, columns in _blocks(output.shape):
        _poll(cancelled)
        block, original = output[row, columns], source[row, columns]
        if not np.isfinite(block).all() or np.any(block < 0.0) or np.any(block > 1.0):
            raise RuntimeError('Lip texture returned invalid SDR output; discarded')
        if np.any(block < original):
            raise RuntimeError('Lip texture returned a darkening correction; discarded')
        if amount == 0.0:
            unchanged = np.array_equal(block.view(np.uint32), original.view(np.uint32))
        else:
            protected = ((weight[row, columns] < FULL_SUPPORT)
                         | np.any(original <= 0.001, axis=-1)
                         | np.any(original >= 0.985, axis=-1))
            unchanged = np.array_equal(block[protected].view(np.uint32), original[protected].view(np.uint32))
        if not unchanged:
            raise RuntimeError('Lip texture changed neutral/unsupported/clipped pixels; discarded')
    _poll(cancelled)
    return output
