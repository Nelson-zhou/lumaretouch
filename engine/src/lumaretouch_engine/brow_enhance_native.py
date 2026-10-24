# SPDX-License-Identifier: GPL-3.0-or-later
"""Original source-local existing-brow contrast ABI boundary. AUTHORED / UNRUN.

Actual target and separate adjacent-forehead reference evidence are required.
No Python algorithm fallback, inference, runtime build, download or profile guess.
"""
import ctypes as C
from functools import lru_cache
import math
from pathlib import Path

import numpy as np

from .cpu_memory_budget import available_estimate as _available_estimate

MAX_PIXELS = 32_000_000
MAX_DIMENSION = 65_536
MIN_RADIUS = 2
MAX_RADIUS = 128
NATIVE_SCRATCH_BYTES_PER_PIXEL = 44
NATIVE_TOTAL_BYTES_PER_PIXEL = 76
ADDITIONAL_BYTES_PER_PIXEL = 76
TOTAL_BYTES_PER_PIXEL = 96
MAX_WORKING_BYTES = 4 * 1024**3
SCRATCH_BYTES = 8 * 1024**2
COPY_PIXELS = 4096
ENCODING = 'encoded-working-srgb-d65-sdr'
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_brow_enhance.so'
    if not path.is_file():
        raise RuntimeError('Brow enhancement Rust core is not installed; no fallback was applied')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_brow_enhance_abi.argtypes = []
        lib.lrt_brow_enhance_abi.restype = C.c_uint32
        if lib.lrt_brow_enhance_abi() != 1:
            raise RuntimeError('Brow enhancement Rust ABI mismatch')
        lib.lrt_brow_enhance_apply_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, P, C.c_size_t,
            C.c_size_t, C.c_size_t, C.c_float, C.c_size_t,
            P, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_brow_enhance_apply_v1.restype = C.c_int
    except (OSError, AttributeError) as error:
        raise RuntimeError('Brow enhancement Rust core cannot load its required ABI') from error
    return lib


def available():
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def memory_estimate(shape):
    """Pure extra memory estimate for exact (H,W), not whole-render admission.

    Includes 20 B/px independent snapshots, 12 output, 44 native peak scratch,
    plus 8 MiB bounded copy/allocator allowance. Caller inputs add 20 B/px to
    the local total; host must also reserve its analysis and other render stages.
    No native load, cgroup read, allocation or source analysis is performed here.
    """
    if type(shape) not in (tuple, list) or len(shape) != 2:
        raise ValueError('Brow enhancement estimate requires exact (height,width)')
    height, width = shape
    if (type(width) is not int or type(height) is not int
            or min(width, height) < 1 or max(width, height) > MAX_DIMENSION):
        raise ValueError('Brow enhancement dimensions are outside the supported range')
    pixels = width * height
    if (pixels > MAX_PIXELS
            or TOTAL_BYTES_PER_PIXEL * pixels + SCRATCH_BYTES > MAX_WORKING_BYTES):
        raise MemoryError('Brow enhancement exceeds its memory/pixel budget; no proxy fallback')
    return ADDITIONAL_BYTES_PER_PIXEL * pixels + SCRATCH_BYTES


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Brow enhancement cancelled; private output discarded')


def _control(value):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError('Brow enhancement amount requires a finite number in [-1,1]')
    try:
        number = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError('Brow enhancement amount requires a finite number in [-1,1]') from error
    if not math.isfinite(number) or not -1.0 <= number <= 1.0:
        raise ValueError('Brow enhancement amount requires a finite number in [-1,1]')
    return number


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
        raise InterruptedError('Brow enhancement cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Brow enhancement Rust resource budget exceeded')
    if code == 6:
        raise RuntimeError('Brow enhancement Rust panic contained; private output discarded')
    if code:
        messages = {1: 'invalid ABI, lengths, dimensions or output aliasing',
                    2: 'invalid signed amount or measured source radius',
                    3: 'nonfinite/non-SDR RGB or coverage, overlapping masks or numerical refusal',
                    7: 'insufficient or heterogeneous actual adjacent-forehead reference'}
        raise ValueError('Brow enhancement Rust refused: ' + messages.get(code, str(code)))


def apply(source_rgb, target_coverage, amount, *, reference_coverage, radius,
          cancelled=lambda: False):
    """Return owned float32 encoded working-sRGB-D65 SDR effected RGB.

    source_rgb is ORIGINAL effective source on this exact grid, never a previous
    enhanced result. Target coverage grants permission only inside source-derived
    existing brow support. Reference coverage is independent actual adjacent
    forehead, disjoint from every positive target pixel. Bare geometry, repeated
    edges, translated copies and estimated/painted replacement RGB are not evidence.
    The host authenticates source revision, face, geometry, reference and exclusions.

    radius is a strict Python int 2..128 derived from this source's measured brow
    extent and reference reach, not a recipe field. The crop contains ALL positive
    target/reference support on the same grid; no radius-dependent edge repetition.
    Native demands mass>=4 and effective count>=4 with local luminance CV<=.25
    for every requested target pixel. Poor reference refuses the whole side.

    Inputs must be exact float32 HWC RGB / HW masks with finite SDR [0,1], even
    at zero strength. Strided inputs are snapshotted separately and must remain
    immutable while copying. No implicit alpha/HDR/profile/dtype conversion.
    Source zeros, unsupported pixels and non-dark residuals remain bit copies.
    Only existing dark contrast is strengthened/reduced, using a bounded common
    linear-RGB gain. No added brow colour, edge synthesis or hair reconstruction.
    """
    amount = _control(amount)
    if type(radius) is not int or not MIN_RADIUS <= radius <= MAX_RADIUS:
        raise ValueError('Brow enhancement radius requires measured integer [2,128]')
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    if type(source_rgb) is not np.ndarray or source_rgb.ndim != 3 or source_rgb.shape[2] != 3:
        raise ValueError('Brow enhancement requires an HWC float32 source RGB array')
    height, width, _ = source_rgb.shape
    _shape(source_rgb, (height, width, 3), 'Source RGB')
    _shape(target_coverage, (height, width), 'Existing brow coverage')
    _shape(reference_coverage, (height, width), 'Actual forehead reference coverage')
    _poll(cancelled)
    if memory_estimate((height, width)) > _available_estimate():
        raise MemoryError('Insufficient CPU memory for independent brow enhancement snapshots and native scratch')
    source = _snapshot(source_rgb, source_rgb.shape, 'Source RGB', cancelled)
    target = _snapshot(target_coverage, target_coverage.shape, 'Existing brow coverage', cancelled)
    reference = _snapshot(reference_coverage, reference_coverage.shape, 'Actual forehead reference coverage', cancelled)
    for row, columns in _blocks(target.shape):
        _poll(cancelled)
        if np.any((target[row, columns] > 0.0) & (reference[row, columns] > 0.0)):
            raise ValueError('Existing brow and actual forehead reference coverage must be disjoint')
    _poll(cancelled)
    lib = native()
    _poll(cancelled)
    output = np.empty_like(source, order='C')
    callback, errors = _callback(cancelled)
    code = lib.lrt_brow_enhance_apply_v1(
        source.ctypes.data_as(P), source.size, target.ctypes.data_as(P), target.size,
        reference.ctypes.data_as(P), reference.size, width, height, amount, radius,
        output.ctypes.data_as(P), output.size, callback, None,
    )
    _result(code, cancelled, errors)
    for row, columns in _blocks(output.shape):
        _poll(cancelled)
        block, original = output[row, columns], source[row, columns]
        if not np.isfinite(block).all() or np.any(block < 0.0) or np.any(block > 1.0):
            raise RuntimeError('Brow enhancement returned invalid SDR output; discarded')
        if amount == 0.0:
            unchanged = np.array_equal(block.view(np.uint32), original.view(np.uint32))
        else:
            protected = ((target[row, columns] == 0.0)
                         | np.all(original == 0.0, axis=-1)
                         | np.all(original == 1.0, axis=-1))
            unchanged = np.array_equal(block[protected].view(np.uint32), original[protected].view(np.uint32))
        if not unchanged:
            raise RuntimeError('Brow enhancement changed neutral/protected pixels; discarded')
        if ((amount > 0.0 and np.any(block > original))
                or (amount < 0.0 and np.any(block < original))):
            raise RuntimeError('Brow enhancement violated signed existing-contrast direction; discarded')
    _poll(cancelled)
    return output
