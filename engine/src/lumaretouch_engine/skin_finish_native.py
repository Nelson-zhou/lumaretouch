# SPDX-License-Identifier: GPL-3.0-or-later
"""Original Rust skin whitening/rosiness boundary. AUTHORED / UNRUN.

No runtime builds/downloads, implicit colour conversion or alternate algorithm.
Geometry, source identity and semantic skin/protection support belong to the host.
"""
import ctypes as C
from functools import lru_cache
import math
from pathlib import Path

import numpy as np

from .cpu_memory_budget import available_estimate as _available_estimate

MAX_PIXELS = 64_000_000
MAX_DIMENSION = 65_536
GAMUT_STEPS = 24
MAX_GAMUT_EVALUATIONS = 1_600_000_000
MAX_WORKING_BYTES = 3 * 1024**3
SCRATCH_BYTES = 8 * 1024**2
COPY_PIXELS = 4096
WHITENING_LIFT = 0.18
WHITENING_CHROMA_REDUCTION = 0.12
WHITENING_COOL_LAB_B = 1.5
ROSINESS_LAB_A = 5.0
ROSINESS_LAB_B_RATIO = 0.25
ROSINESS_RED_RESTRAINT = 20.0
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_skin_finish.so'
    if not path.is_file():
        raise RuntimeError('Skin whitening/rosiness Rust core is not installed; no fallback was applied')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_skin_finish_abi.argtypes = []
        lib.lrt_skin_finish_abi.restype = C.c_uint32
        if lib.lrt_skin_finish_abi() != 1:
            raise RuntimeError('Skin whitening/rosiness Rust ABI mismatch')
        lib.lrt_skin_finish_apply_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t,
            C.c_float, C.c_float, P, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_skin_finish_apply_v1.restype = C.c_int
    except (OSError, AttributeError) as error:
        raise RuntimeError('Skin whitening/rosiness Rust core cannot load its required ABI') from error
    return lib


def available():
    """Check actual loading and required ABI/symbols, not mere file existence."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Skin whitening/rosiness cancelled; private output discarded')


def _control(value, label):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError(label + ' requires a finite number in [0,1]')
    try:
        number = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(label + ' requires a finite number in [0,1]') from error
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(label + ' requires a finite number in [0,1]')
    return number


def _shape(array, shape, label):
    if type(array) is not np.ndarray or array.dtype != np.float32 or array.shape != shape:
        raise ValueError(label + ' requires exact native float32 shape ' + str(shape))


def _admit(width, height):
    if (type(width) is not int or type(height) is not int
            or min(width, height) < 1 or max(width, height) > MAX_DIMENSION):
        raise ValueError('Skin whitening/rosiness dimensions are outside the supported range')
    pixels = width * height
    if pixels > MAX_PIXELS or pixels * (GAMUT_STEPS + 1) > MAX_GAMUT_EVALUATIONS:
        raise MemoryError('Skin whitening/rosiness exceeds its native work budget; no proxy fallback')
    # Caller RGB/mask 16 B/px + independent snapshots 16 + private output 12.
    # Native kernel uses constant stack space, no image-sized scratch or heap.
    if 44 * pixels + SCRATCH_BYTES > MAX_WORKING_BYTES:
        raise MemoryError('Skin whitening/rosiness exceeds its memory budget; no proxy fallback')
    additional = 28 * pixels + SCRATCH_BYTES
    if additional > _available_estimate():
        raise MemoryError('Insufficient CPU memory for independent skin finish snapshots')
    return additional


def _blocks(shape):
    # Limit validation/copy temporaries and cancellation latency even on wide ROIs.
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
    _poll(cancelled)
    snapshot.setflags(write=False)
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
        raise InterruptedError('Skin whitening/rosiness cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Skin whitening/rosiness Rust resource budget exceeded')
    if code == 6:
        raise RuntimeError('Skin whitening/rosiness Rust panic contained; private output discarded')
    if code:
        messages = {1: 'invalid ABI, lengths, dimensions or buffer aliasing',
                    2: 'invalid whitening or rosiness',
                    3: 'nonfinite or non-SDR RGB/coverage'}
        raise ValueError('Skin whitening/rosiness Rust refused: ' + messages.get(code, str(code)))


def apply(rgb, coverage, whitening, rosiness, *, cancelled=lambda: False):
    """Return an owned C-contiguous float32 HWC encoded working-sRGB SDR array.

    Both controls are [0,1], with zero neutral. Whitening adds up to 4.5 L*
    with a strictly monotone endpoint-preserving curve and restrained cool-white
    chroma. Rosiness uses a bounded warm-red vector with luminance gating and
    already-red restraint, at unchanged whitening-adjusted L*. No exposure,
    temperature/tint, blur or texture-synthesis aliases. Strict common-chroma
    feasibility reduction avoids RGB clipping. Coverage blends in linear light.
    See core/skin_finish/README.md for exact formula and mathematical limits.

    The host must supply authenticated source/face/revision/transform ownership,
    geometry and actual semantic skin coverage with protections/exclusions.
    A bare face rectangle is not skin evidence. This kernel cannot verify anatomy
    or source identity. It reads no neighbours and cannot detect/repair occlusion.

    Inputs must not mutate during snapshot copying. Native reads then use owned
    read-only snapshots. No input is retained/mutated, and errors or cancellation
    never return partial output. Neutral controls and zero coverage are bit-exact.
    All values must be finite SDR [0,1], even on unsupported/neutral pixels.
    Alpha, tensors, HDR, wrong dtypes/shapes and implicit colour-space conversions
    are rejected. Numerical arrays cannot prove that the host supplied sRGB.
    """
    whitening = _control(whitening, 'Whitening')
    rosiness = _control(rosiness, 'Rosiness')
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    if type(rgb) is not np.ndarray or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Skin whitening/rosiness requires an HWC float32 RGB array')
    height, width, _ = rgb.shape
    _shape(rgb, (height, width, 3), 'RGB')
    _shape(coverage, (height, width), 'Skin coverage')
    _poll(cancelled)
    _admit(width, height)
    source = _snapshot(rgb, rgb.shape, 'RGB', cancelled)
    weight = _snapshot(coverage, coverage.shape, 'Skin coverage', cancelled)
    _poll(cancelled)
    lib = native()
    _poll(cancelled)
    output = np.empty_like(source, order='C')
    callback, errors = _callback(cancelled)
    code = lib.lrt_skin_finish_apply_v1(
        source.ctypes.data_as(P), source.size, weight.ctypes.data_as(P), weight.size,
        width, height, whitening, rosiness,
        output.ctypes.data_as(P), output.size, callback, None,
    )
    _result(code, cancelled, errors)
    neutral = whitening == 0.0 and rosiness == 0.0
    for row, columns in _blocks(output.shape):
        _poll(cancelled)
        block, original = output[row, columns], source[row, columns]
        if not np.isfinite(block).all() or np.any(block < 0.0) or np.any(block > 1.0):
            raise RuntimeError('Skin whitening/rosiness returned invalid SDR output; discarded')
        if neutral:
            unchanged = np.array_equal(block.view(np.uint32), original.view(np.uint32))
        else:
            protected = ((weight[row, columns] == 0.0)
                         | np.all(original == 0.0, axis=-1)
                         | np.all(original == 1.0, axis=-1))
            unchanged = np.array_equal(block[protected].view(np.uint32), original[protected].view(np.uint32))
        if not unchanged:
            raise RuntimeError('Skin whitening/rosiness changed neutral or unsupported pixels or endpoints; discarded')
    _poll(cancelled)
    return output
