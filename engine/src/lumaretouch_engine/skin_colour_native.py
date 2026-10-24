"""Original Rust face-skin temperature/tint boundary. AUTHORED / UNRUN.

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
TEMPERATURE_LAB_B = 8.0
TINT_LAB_A = 6.0
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_skin_colour.so'
    if not path.is_file():
        raise RuntimeError('Skin temperature/tint Rust core is not installed; no fallback was applied')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_skin_colour_abi.argtypes = []
        lib.lrt_skin_colour_abi.restype = C.c_uint32
        if lib.lrt_skin_colour_abi() != 1:
            raise RuntimeError('Skin temperature/tint Rust ABI mismatch')
        lib.lrt_skin_colour_apply_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t,
            C.c_float, C.c_float, P, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_skin_colour_apply_v1.restype = C.c_int
    except (OSError, AttributeError) as error:
        raise RuntimeError('Skin temperature/tint Rust core cannot load its required ABI') from error
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
        raise InterruptedError('Skin temperature/tint cancelled; private output discarded')


def _control(value, label):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError(label + ' requires a finite number in [-1,1]')
    try:
        number = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(label + ' requires a finite number in [-1,1]') from error
    if not math.isfinite(number) or not -1.0 <= number <= 1.0:
        raise ValueError(label + ' requires a finite number in [-1,1]')
    return number


def _shape(array, shape, label):
    if type(array) is not np.ndarray or array.dtype != np.float32 or array.shape != shape:
        raise ValueError(label + ' requires exact native float32 shape ' + str(shape))


def _admit(width, height):
    if (type(width) is not int or type(height) is not int
            or min(width, height) < 1 or max(width, height) > MAX_DIMENSION):
        raise ValueError('Skin temperature/tint dimensions are outside the supported range')
    pixels = width * height
    if pixels > MAX_PIXELS or pixels * (GAMUT_STEPS + 1) > MAX_GAMUT_EVALUATIONS:
        raise MemoryError('Skin temperature/tint exceeds its native work budget; no proxy fallback')
    # Caller RGB/mask 16 B/px + independent snapshots 16 + private output 12.
    # Native kernel uses constant stack space, no image-sized scratch or heap.
    if 44 * pixels + SCRATCH_BYTES > MAX_WORKING_BYTES:
        raise MemoryError('Skin temperature/tint exceeds its memory budget; no proxy fallback')
    additional = 28 * pixels + SCRATCH_BYTES
    if additional > _available_estimate():
        raise MemoryError('Insufficient CPU memory for independent skin colour snapshots')
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
        raise InterruptedError('Skin temperature/tint cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Skin temperature/tint Rust resource budget exceeded')
    if code == 6:
        raise RuntimeError('Skin temperature/tint Rust panic contained; private output discarded')
    if code:
        messages = {1: 'invalid ABI, lengths, dimensions or buffer aliasing',
                    2: 'invalid temperature or tint',
                    3: 'nonfinite or non-SDR RGB/coverage'}
        raise ValueError('Skin temperature/tint Rust refused: ' + messages.get(code, str(code)))


def apply(rgb, coverage, temperature, tint, *, cancelled=lambda: False):
    """Return an owned C-contiguous float32 HWC encoded working-sRGB SDR array.

    temperature/tint are bounded [-1,1] controls, NOT Kelvin/Adobe equivalents.
    The original scales are ±8 CIELAB b* (warm yellow/cool blue) and ±6 a*
    (magenta/green). L* stays fixed; common-chroma compression avoids RGB clips.
    Coverage mixes the corrected pixel with its own original in linear light.

    The host must supply authenticated source/face/revision/transform ownership,
    geometry and actual semantic face-skin coverage with protections/exclusions.
    A bare face rectangle is not skin evidence. This kernel cannot verify anatomy
    or source identity. It reads no neighbours and cannot detect/repair occlusion.

    Inputs must not mutate during snapshot copying. Native reads then use owned
    read-only snapshots. No input is retained/mutated, and errors or cancellation
    never return partial output. Neutral controls and zero coverage are bit-exact.
    All values must be finite SDR [0,1], even on unsupported/neutral pixels.
    Alpha, tensors, HDR, wrong dtypes/shapes and implicit colour-space conversions
    are rejected. Numerical arrays cannot prove that the host supplied sRGB.
    """
    temperature = _control(temperature, 'Temperature')
    tint = _control(tint, 'Tint')
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    if type(rgb) is not np.ndarray or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Skin temperature/tint requires an HWC float32 RGB array')
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
    code = lib.lrt_skin_colour_apply_v1(
        source.ctypes.data_as(P), source.size, weight.ctypes.data_as(P), weight.size,
        width, height, temperature, tint,
        output.ctypes.data_as(P), output.size, callback, None,
    )
    _result(code, cancelled, errors)
    neutral = temperature == 0.0 and tint == 0.0
    for row, columns in _blocks(output.shape):
        _poll(cancelled)
        block, original = output[row, columns], source[row, columns]
        if not np.isfinite(block).all() or np.any(block < 0.0) or np.any(block > 1.0):
            raise RuntimeError('Skin temperature/tint returned invalid SDR output; discarded')
        if neutral:
            unchanged = np.array_equal(block.view(np.uint32), original.view(np.uint32))
        else:
            outside = weight[row, columns] == 0.0
            unchanged = np.array_equal(block[outside].view(np.uint32), original[outside].view(np.uint32))
        if not unchanged:
            raise RuntimeError('Skin temperature/tint changed neutral or unsupported pixels; discarded')
    _poll(cancelled)
    return output
