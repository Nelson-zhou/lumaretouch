"""Original Rust eye-white purification bridge. AUTHORED / UNRUN.

One kernel for NumPy and explicitly staged Torch hosts. No runtime compilation,
download, implicit colour conversion, fallback whitening or second algorithm.
"""
import ctypes as C
from functools import lru_cache
import math
from pathlib import Path

import numpy as np

from .cpu_memory_budget import available_estimate as _available_estimate

MAX_PIXELS = 64_000_000
MAX_DIMENSION = 65_536
MAX_RADIUS = 32
MAX_NEIGHBOUR_VISITS = 64_000_000
DONOR_COVERAGE = 0.75
MAX_WORKING_BYTES = 3 * 1024**3
SCRATCH_BYTES = 8 * 1024**2
POLL_PIXELS = 4096
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_sclera_purify.so'
    if not path.is_file():
        raise RuntimeError('Eye-white purification Rust core is not installed; no fallback was applied')
    lib = C.CDLL(str(path))
    lib.lrt_sclera_purify_abi.argtypes = []
    lib.lrt_sclera_purify_abi.restype = C.c_uint32
    if lib.lrt_sclera_purify_abi() != 1:
        raise RuntimeError('Eye-white purification Rust ABI mismatch')
    lib.lrt_sclera_purify_apply_v1.argtypes = [
        P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t,
        C.c_float, C.c_size_t, P, C.c_size_t, CANCEL, C.c_void_p,
    ]
    lib.lrt_sclera_purify_apply_v1.restype = C.c_int
    return lib


def available():
    """Load and inspect the real ABI/symbols; a file alone is not availability."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Eye-white purification cancelled; private output discarded')


def _amount(value):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError('Purification amount requires a finite number in [0,1]')
    try:
        number = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError('Purification amount requires a finite number in [0,1]') from error
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError('Purification amount requires a finite number in [0,1]')
    return number


def _radius(value):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, np.integer))
            or not 1 <= value <= MAX_RADIUS):
        raise ValueError('Purification radius requires an integer in [1,32]; no silent cap')
    return int(value)


def _shape(array, shape, label):
    if type(array) is not np.ndarray or array.dtype != np.float32 or array.shape != shape:
        raise ValueError(label + ' requires exact float32 shape ' + str(shape))


def _admit(width, height, radius):
    if (type(width) is not int or type(height) is not int
            or min(width, height) < 1 or max(width, height) > MAX_DIMENSION):
        raise ValueError('Eye-white purification dimensions are outside the supported ROI range')
    radius = _radius(radius)
    pixels = width * height
    # Count every footprint position conservatively, including unsupported and
    # out-of-ROI candidates, so sparse masks cannot evade the work bound.
    visits = pixels * (2 * radius + 1)**2
    if pixels > MAX_PIXELS or visits > MAX_NEIGHBOUR_VISITS:
        raise MemoryError('Eye-white purification exceeds its native work budget; no proxy fallback')
    # Caller RGB/mask 16 B/px + snapshots 16 + output 12 + native f64 Y 8.
    # Fixed 4225-element sorting window and row validation fit the allowance.
    if 52 * pixels + SCRATCH_BYTES > MAX_WORKING_BYTES:
        raise MemoryError('Eye-white purification exceeds its memory budget; no proxy fallback')
    additional = 36 * pixels + SCRATCH_BYTES
    if additional > _available_estimate():
        raise MemoryError('Insufficient CPU memory for independent eye-white purification snapshots')
    return additional


def _snapshot(array, shape, label, cancelled):
    _shape(array, shape, label)
    _poll(cancelled)
    # Own even contiguous/read-only input: its owning base might be mutable.
    snapshot = np.empty(shape, dtype=np.float32, order='C')
    rows = max(1, POLL_PIXELS // shape[1])
    for start in range(0, shape[0], rows):
        _poll(cancelled)
        block = snapshot[start:start + rows]
        block[...] = array[start:start + rows]
        if not np.isfinite(block).all() or np.any(block < 0.0) or np.any(block > 1.0):
            raise ValueError(label + ' requires finite SDR [0,1] values; no clipping')
    _poll(cancelled)
    snapshot.setflags(write=False)
    return snapshot


def _callback(cancelled):
    errors = []
    def poll(_context):
        try:
            return int(bool(cancelled()))
        except BaseException as error:
            if not errors:
                errors.append(error)
            return 1
    return CANCEL(poll), errors


def _result(code, cancelled, errors):
    if errors:
        raise errors[0]
    if code == 4:
        raise InterruptedError('Eye-white purification cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Eye-white purification Rust resource budget exceeded')
    if code == 6:
        raise RuntimeError('Eye-white purification Rust panic contained; private output discarded')
    if code:
        messages = {1: 'invalid ABI, lengths, dimensions or buffer aliasing',
                    2: 'invalid purification amount or radius',
                    3: 'nonfinite or non-SDR RGB/coverage'}
        raise ValueError('Eye-white purification Rust refused: ' + messages.get(code, str(code)))


def apply(rgb, coverage, amount, radius, *, cancelled=lambda: False):
    """Return owned contiguous float32 HWC encoded working-sRGB for ONE eye ROI.

    The host authenticates source/face/eye/revision/transform and supplies actual
    sclera-candidate coverage, not a bare eye rectangle. Its geometric/photometric
    heuristic does not certify anatomy or occlusion. Positive coverage selects
    targets; only coverage >=0.75 supplies donor statistics. Radius is an explicit
    integer in this source raster's pixels, 1..32. It is never inferred/capped here.

    The caller must not mutate inputs during snapshot copying. Subsequent native
    reads use independently owned read-only snapshots. No caller buffer is
    mutated or retained, and failure/cancellation never returns partial output.
    Finite SDR [0,1] input is mandatory even for neutral settings or zero coverage.
    Alpha, HDR, float16 and implicit tensor conversion are rejected. Numerical
    arrays cannot identify their colour space: the host must convert other spaces.
    """
    strength = _amount(amount)
    source_radius = _radius(radius)
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    if type(rgb) is not np.ndarray or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Eye-white purification requires an HWC float32 RGB array')
    height, width, _ = rgb.shape
    _shape(rgb, (height, width, 3), 'RGB')
    _shape(coverage, (height, width), 'Sclera coverage')
    _poll(cancelled)
    _admit(width, height, source_radius)
    source = _snapshot(rgb, rgb.shape, 'RGB', cancelled)
    weight = _snapshot(coverage, coverage.shape, 'Sclera coverage', cancelled)
    _poll(cancelled)
    lib = native()
    output = np.empty_like(source, order='C')
    callback, errors = _callback(cancelled)
    code = lib.lrt_sclera_purify_apply_v1(
        source.ctypes.data_as(P), source.size,
        weight.ctypes.data_as(P), weight.size,
        width, height, strength, source_radius,
        output.ctypes.data_as(P), output.size, callback, None,
    )
    _result(code, cancelled, errors)
    for index, row in enumerate(output):
        _poll(cancelled)
        if not np.isfinite(row).all() or np.any(row < 0.0) or np.any(row > 1.0):
            raise RuntimeError('Eye-white purification returned invalid SDR output; discarded')
        original = source[index]
        if strength == 0.0:
            unchanged = np.array_equal(row.view(np.uint32), original.view(np.uint32))
        else:
            outside = weight[index] == 0.0
            unchanged = np.array_equal(row[outside].view(np.uint32), original[outside].view(np.uint32))
        if not unchanged:
            raise RuntimeError('Eye-white purification changed neutral or unsupported pixels; discarded')
    _poll(cancelled)
    return output
