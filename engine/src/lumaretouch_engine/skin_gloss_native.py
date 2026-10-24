# SPDX-License-Identifier: GPL-3.0-or-later
"""Original source-measured face-skin gloss Rust boundary. AUTHORED / UNRUN.

The boundary uses encoded working-sRGB-D65 float32 SDR, matching skin colour and
finish. Rust estimates ORIGINAL-source evidence and corrects the CURRENT colour
then finish intermediate in linear light. No Python algorithm fallback or build.
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
MAX_RADIUS = 256
NATIVE_SCRATCH_BYTES_PER_PIXEL = 44
NATIVE_TOTAL_BYTES_PER_PIXEL = 84
ADDITIONAL_BYTES_PER_PIXEL = 84
TOTAL_BYTES_PER_PIXEL = 112
MAX_WORKING_BYTES = 4 * 1024**3
SCRATCH_BYTES = 8 * 1024**2
COPY_PIXELS = 4096
ENCODING = 'encoded-working-srgb-d65-sdr'
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_skin_gloss.so'
    if not path.is_file():
        raise RuntimeError('Skin gloss Rust core is not installed; no fallback was applied')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_skin_gloss_abi.argtypes = []
        lib.lrt_skin_gloss_abi.restype = C.c_uint32
        if lib.lrt_skin_gloss_abi() != 1:
            raise RuntimeError('Skin gloss Rust ABI mismatch')
        lib.lrt_skin_gloss_apply_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, P, C.c_size_t,
            C.c_size_t, C.c_size_t, C.c_float, C.c_size_t,
            P, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_skin_gloss_apply_v1.restype = C.c_int
    except (OSError, AttributeError) as error:
        raise RuntimeError('Skin gloss Rust core cannot load its required ABI') from error
    return lib


def available():
    """Actual required symbol/ABI loading only, not photographic availability."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def memory_estimate(shape):
    """Return additional snapshot/output/native estimate for exact (H,W).

    No native loading, live cgroup read, allocations or source analysis. The
    estimate includes 28 B/px snapshots, 12 B/px output, 44 B/px peak native scratch,
    and 8 MiB bounded copy/allocator allowance. This is not an OOM guarantee or a
    replacement for the host's combined render/anatomy/current-image admission.
    """
    if type(shape) not in (tuple, list) or len(shape) != 2:
        raise ValueError('Skin gloss memory estimate requires exact (height,width)')
    height, width = shape
    if (type(width) is not int or type(height) is not int
            or min(width, height) < 1 or max(width, height) > MAX_DIMENSION):
        raise ValueError('Skin gloss dimensions are outside the supported range')
    pixels = width * height
    if (pixels > MAX_PIXELS
            or TOTAL_BYTES_PER_PIXEL * pixels + SCRATCH_BYTES > MAX_WORKING_BYTES):
        raise MemoryError('Skin gloss exceeds its memory/pixel budget; no proxy fallback')
    return ADDITIONAL_BYTES_PER_PIXEL * pixels + SCRATCH_BYTES


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Skin gloss cancelled; private output discarded')


def _control(value):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError('Skin gloss amount requires a finite number in [-1,1]')
    try:
        number = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError('Skin gloss amount requires a finite number in [-1,1]') from error
    if not math.isfinite(number) or not -1.0 <= number <= 1.0:
        raise ValueError('Skin gloss amount requires a finite number in [-1,1]')
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
        raise InterruptedError('Skin gloss cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Skin gloss Rust resource budget exceeded')
    if code == 6:
        raise RuntimeError('Skin gloss Rust panic contained; private output discarded')
    if code:
        messages = {1: 'invalid ABI, lengths, dimensions or buffer aliasing',
                    2: 'invalid signed amount or face-scale radius',
                    3: 'nonfinite or non-SDR RGB/coverage or numerical refusal'}
        raise ValueError('Skin gloss Rust refused: ' + messages.get(code, str(code)))


def apply(current_rgb, coverage, amount, *, reference_rgb, radius, cancelled=lambda: False):
    """Return owned C-contiguous float32 encoded working-sRGB-D65 SDR RGB.

    current_rgb is the colour→finish intermediate. reference_rgb is REQUIRED
    ORIGINAL effective source on the exact same grid, independent of colour,
    finish and gloss edits. The host authenticates source/revision/face/transform,
    mask evidence and exclusions; arrays cannot establish those facts. Coverage
    is genuine face-skin permission, not a rectangle or invented specular mask.

    radius is a strict Python int 2..256, derived by the host from measured face
    scale in this render grid, not a portable recipe parameter. Estimate on the
    complete original grid or at least a real 2*radius halo before cropping output.
    No resampling, invented halo or repeat application to a previous gloss result.

    The source-only local linear-light fit requires bright/reduced-chroma,
    coherent non-achromatic skin evidence and a neutral-light residual. Broad
    supported existing highlights alone receive bounded signed neutral-light
    adjustment. Flat/achromatic/clipped/unsupported/poor-fit data is unchanged;
    ambiguous coloured illumination cannot be universally diagnosed from one
    image. This is a conservative appearance edit, not physical recovery.

    Neutral/zero support and pure black/white current endpoints are bit copies.
    Inputs are finite SDR [0,1] even when neutral, exact float32 HWC RGB/HW mask;
    alpha, HDR, tensors and implicit transfer/profile conversions are refused.
    Strided arrays are allowed but snapshot independently. Inputs must remain
    immutable during snapshotting. No input mutation, retained buffers, partial
    output publication, runtime build/download or alternate Python algorithm.
    """
    amount = _control(amount)
    if type(radius) is not int or not MIN_RADIUS <= radius <= MAX_RADIUS:
        raise ValueError('Skin gloss radius requires an integer in [2,256] from measured face scale')
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    if type(current_rgb) is not np.ndarray or current_rgb.ndim != 3 or current_rgb.shape[2] != 3:
        raise ValueError('Skin gloss requires an HWC float32 current RGB array')
    height, width, _ = current_rgb.shape
    _shape(current_rgb, (height, width, 3), 'Current RGB')
    _shape(reference_rgb, (height, width, 3), 'Original reference RGB')
    _shape(coverage, (height, width), 'Face skin coverage')
    _poll(cancelled)
    additional = memory_estimate((height, width))
    if additional > _available_estimate():
        raise MemoryError('Insufficient CPU memory for independent skin gloss snapshots and native scratch')
    current = _snapshot(current_rgb, current_rgb.shape, 'Current RGB', cancelled)
    reference = _snapshot(reference_rgb, reference_rgb.shape, 'Original reference RGB', cancelled)
    weight = _snapshot(coverage, coverage.shape, 'Face skin coverage', cancelled)
    _poll(cancelled)
    lib = native()
    _poll(cancelled)
    output = np.empty_like(current, order='C')
    callback, errors = _callback(cancelled)
    code = lib.lrt_skin_gloss_apply_v1(
        current.ctypes.data_as(P), current.size,
        reference.ctypes.data_as(P), reference.size,
        weight.ctypes.data_as(P), weight.size,
        width, height, amount, radius, output.ctypes.data_as(P), output.size,
        callback, None,
    )
    _result(code, cancelled, errors)
    for row, columns in _blocks(output.shape):
        _poll(cancelled)
        block, original = output[row, columns], current[row, columns]
        if not np.isfinite(block).all() or np.any(block < 0.0) or np.any(block > 1.0):
            raise RuntimeError('Skin gloss returned invalid SDR output; discarded')
        if amount == 0.0:
            unchanged = np.array_equal(block.view(np.uint32), original.view(np.uint32))
        else:
            protected = ((weight[row, columns] == 0.0)
                         | np.all(original == 0.0, axis=-1)
                         | np.all(original == 1.0, axis=-1))
            unchanged = np.array_equal(block[protected].view(np.uint32), original[protected].view(np.uint32))
        if not unchanged:
            raise RuntimeError('Skin gloss changed neutral or unsupported pixels or endpoints; discarded')
    _poll(cancelled)
    return output
