# SPDX-License-Identifier: GPL-3.0-or-later
"""Original source-owned skin texture/fine-sharpening Rust ABI. AUTHORED / UNRUN.

Working boundary: encoded working-sRGB-D65 float32 SDR. Source-only normalized
guided log-luminance bands drive a bounded common linear-RGB multiplier on the
current colour→finish→gloss intermediate. No Python algorithm fallback or build.
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
NATIVE_SCRATCH_BYTES_PER_PIXEL = 72
NATIVE_TOTAL_BYTES_PER_PIXEL = 112
ADDITIONAL_BYTES_PER_PIXEL = 112
TOTAL_BYTES_PER_PIXEL = 140
MAX_WORKING_BYTES = 4 * 1024**3
SCRATCH_BYTES = 8 * 1024**2
COPY_PIXELS = 4096
ENCODING = 'encoded-working-srgb-d65-sdr'
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_skin_texture.so'
    if not path.is_file():
        raise RuntimeError('Skin texture Rust core is not installed; no fallback was applied')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_skin_texture_abi.argtypes = []
        lib.lrt_skin_texture_abi.restype = C.c_uint32
        if lib.lrt_skin_texture_abi() != 1:
            raise RuntimeError('Skin texture Rust ABI mismatch')
        lib.lrt_skin_texture_apply_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, P, C.c_size_t,
            C.c_size_t, C.c_size_t, C.c_float, C.c_float, C.c_size_t,
            P, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_skin_texture_apply_v1.restype = C.c_int
    except (OSError, AttributeError) as error:
        raise RuntimeError('Skin texture Rust core cannot load its required ABI') from error
    return lib


def available():
    """Required symbol/ABI loading only, not semantic/photo acceptance."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def memory_estimate(shape):
    """Pure additional snapshot/output/native estimate for exact (H,W).

    28 B/px independent snapshots + 12 B/px private output + 72 B/px peak
    native scratch, plus 8 MiB allowance. Caller inputs add another 28 B/px.
    This does not load native code, read cgroup state or allocate image buffers.
    Host must separately admit combined render/anatomy/current-image peaks.
    Resource ceilings are not latency guarantees or OOM guarantees.
    """
    if type(shape) not in (tuple, list) or len(shape) != 2:
        raise ValueError('Skin texture memory estimate requires exact (height,width)')
    height, width = shape
    if (type(width) is not int or type(height) is not int
            or min(width, height) < 1 or max(width, height) > MAX_DIMENSION):
        raise ValueError('Skin texture dimensions are outside the supported range')
    pixels = width * height
    if (pixels > MAX_PIXELS
            or TOTAL_BYTES_PER_PIXEL * pixels + SCRATCH_BYTES > MAX_WORKING_BYTES):
        raise MemoryError('Skin texture exceeds its memory/pixel budget; no proxy fallback')
    return ADDITIONAL_BYTES_PER_PIXEL * pixels + SCRATCH_BYTES


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Skin texture cancelled; private output discarded')


def _control(value, label, low):
    message = 'Skin ' + label + ' requires a finite number in [' + str(low) + ',1]'
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError(message)
    try:
        number = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(message) from error
    if not math.isfinite(number) or not low <= number <= 1.0:
        raise ValueError(message)
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
        raise InterruptedError('Skin texture cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Skin texture Rust resource budget exceeded')
    if code == 6:
        raise RuntimeError('Skin texture Rust panic contained; private output discarded')
    if code:
        messages = {1: 'invalid ABI, lengths, dimensions or buffer aliasing',
                    2: 'invalid texture/clarity or face-scale radius',
                    3: 'nonfinite or non-SDR RGB/coverage or numerical refusal'}
        raise ValueError('Skin texture Rust refused: ' + messages.get(code, str(code)))


def apply(current_rgb, coverage, texture, clarity, *, reference_rgb, radius, cancelled=lambda: False):
    """Return owned C-contiguous float32 encoded working-sRGB-D65 SDR RGB.

    reference_rgb is REQUIRED immutable ORIGINAL effective source on the exact
    same grid. current_rgb is the colour→finish→gloss intermediate. The host
    authenticates photograph/revision/person/transform, face-skin evidence and
    exclusions. Arrays cannot authenticate this. A rectangle is not permission.

    texture[-1,1] changes a medium-frequency source band in either direction;
    clarity[0,1] increases a separate fine band, not coarse local contrast. Source
    measurements drive both, never the current intermediate or a previous result.
    This is original edge-aware detail processing, not AI or blemish removal.
    Noise/edge gates are conservative heuristics, not proof of signal separation.

    radius is a strict Python int 4..256, measured in pixels on THIS render grid.
    Fine radius is max(1,radius//4). Both guided scales independently read original
    source; their coefficients use normalized valid-support-only neighborhoods.
    Evaluate on the full original grid or a genuine 2*radius halo, then crop the
    output. No replicated, synthetic, unsupported or other-person halo samples.

    Controls both zero, zero support and current pure black/white endpoints are
    bit copies. All inputs are still validated finite SDR[0,1], exact float32 HWC
    RGB/HW mask. Alpha/HDR/tensors/implicit color conversion are refused. Strides
    are allowed via independent read-only snapshots; caller must not mutate while
    snapshotting. No input mutation/retention, partial publication or runtime build.
    """
    texture = _control(texture, 'texture', -1)
    clarity = _control(clarity, 'clarity', 0)
    if type(radius) is not int or not MIN_RADIUS <= radius <= MAX_RADIUS:
        raise ValueError('Skin texture radius requires an integer in [4,256] from measured face scale')
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    if type(current_rgb) is not np.ndarray or current_rgb.ndim != 3 or current_rgb.shape[2] != 3:
        raise ValueError('Skin texture requires an HWC float32 current RGB array')
    height, width, _ = current_rgb.shape
    _shape(current_rgb, (height, width, 3), 'Current RGB')
    _shape(reference_rgb, (height, width, 3), 'Original reference RGB')
    _shape(coverage, (height, width), 'Face skin coverage')
    _poll(cancelled)
    additional = memory_estimate((height, width))
    if additional > _available_estimate():
        raise MemoryError('Insufficient CPU memory for independent skin texture snapshots and native scratch')
    current = _snapshot(current_rgb, current_rgb.shape, 'Current RGB', cancelled)
    reference = _snapshot(reference_rgb, reference_rgb.shape, 'Original reference RGB', cancelled)
    weight = _snapshot(coverage, coverage.shape, 'Face skin coverage', cancelled)
    _poll(cancelled)
    lib = native()
    _poll(cancelled)
    output = np.empty_like(current, order='C')
    callback, errors = _callback(cancelled)
    code = lib.lrt_skin_texture_apply_v1(
        current.ctypes.data_as(P), current.size,
        reference.ctypes.data_as(P), reference.size,
        weight.ctypes.data_as(P), weight.size,
        width, height, texture, clarity, radius, output.ctypes.data_as(P), output.size,
        callback, None,
    )
    _result(code, cancelled, errors)
    for row, columns in _blocks(output.shape):
        _poll(cancelled)
        block, original = output[row, columns], current[row, columns]
        if not np.isfinite(block).all() or np.any(block < 0.0) or np.any(block > 1.0):
            raise RuntimeError('Skin texture returned invalid SDR output; discarded')
        if texture == 0.0 and clarity == 0.0:
            unchanged = np.array_equal(block.view(np.uint32), original.view(np.uint32))
        else:
            protected = ((weight[row, columns] == 0.0)
                         | np.all(original == 0.0, axis=-1)
                         | np.all(original == 1.0, axis=-1))
            unchanged = np.array_equal(block[protected].view(np.uint32), original[protected].view(np.uint32))
        if not unchanged:
            raise RuntimeError('Skin texture changed neutral or unsupported pixels or endpoints; discarded')
    _poll(cancelled)
    return output
