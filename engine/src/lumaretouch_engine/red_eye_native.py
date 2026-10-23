"""Original Rust flash red-eye bridge. AUTHORED / UNRUN, no acceptance claim.

One colour implementation for NumPy and explicitly CPU-staged Torch hosts.
No runtime compilation, Python colour fallback, download, inference or eye
segmentation. Target-owned inward central-iris candidates come from the host.
"""
import ctypes as C
from functools import lru_cache
import math
from pathlib import Path

import numpy as np

from .cpu_memory_budget import available_estimate as _available_estimate

MAX_PIXELS = 64_000_000
MAX_DIMENSION = 65_536
MAX_WORKING_BYTES = 3 * 1024**3
SCRATCH_BYTES = 8 * 1024**2
POLL_PIXELS = 4096
P = C.POINTER(C.c_float)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_red_eye.so'
    if not path.is_file():
        raise RuntimeError('Red-eye Rust core is not installed; no fallback was applied')
    lib = C.CDLL(str(path))
    lib.lrt_red_eye_abi.argtypes = []
    lib.lrt_red_eye_abi.restype = C.c_uint32
    if lib.lrt_red_eye_abi() != 1:
        raise RuntimeError('Red-eye Rust ABI mismatch')
    lib.lrt_red_eye_apply_v1.argtypes = [
        P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t,
        C.c_float, P, C.c_size_t, CANCEL, C.c_void_p,
    ]
    lib.lrt_red_eye_apply_v1.restype = C.c_int
    return lib


def available():
    """Load and verify the actual ABI/symbols, not merely a file's existence."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Red-eye cancelled; private output discarded')


def _amount(value):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError('Red-eye amount requires a finite number in [0,1]')
    try:
        number = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError('Red-eye amount requires a finite number in [0,1]') from error
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError('Red-eye amount requires a finite number in [0,1]')
    return number


def _shape(array, shape, label):
    if type(array) is not np.ndarray or array.dtype != np.float32 or array.shape != shape:
        raise ValueError(label + ' requires exact float32 shape ' + str(shape))


def _admit(width, height):
    if (type(width) is not int or type(height) is not int
            or min(width, height) < 1 or max(width, height) > MAX_DIMENSION):
        raise ValueError('Red-eye dimensions are outside the supported canvas range')
    pixels = width * height
    # Caller RGB/support 16 B/px + owned snapshots 16 B/px + output 12 B/px.
    # The native kernel allocates nothing. Validation uses bounded row scratch.
    if pixels > MAX_PIXELS or 44 * pixels + SCRATCH_BYTES > MAX_WORKING_BYTES:
        raise MemoryError('Red-eye exceeds its full-resolution memory budget; no proxy fallback')
    additional = 28 * pixels + SCRATCH_BYTES
    if additional > _available_estimate():
        raise MemoryError('Insufficient CPU memory for independent red-eye snapshots')
    return additional


def _snapshot(array, shape, label, cancelled):
    _shape(array, shape, label)
    _poll(cancelled)
    # Own both buffers even when input is contiguous/read-only: a writable base
    # could otherwise change storage concurrently while native code reads it.
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
            # Exceptions cannot unwind across ctypes/C. Stop first, re-raise on
            # the Python side later, and never publish a partially written frame.
            if not errors:
                errors.append(error)
            return 1
    return CANCEL(poll), errors


def _result(code, cancelled, errors):
    if errors:
        raise errors[0]
    if code == 4:
        raise InterruptedError('Red-eye cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Red-eye Rust resource budget exceeded')
    if code == 6:
        raise RuntimeError('Red-eye Rust panic contained; private output discarded')
    if code:
        messages = {1: 'invalid ABI, lengths, dimensions or buffer aliasing',
                    2: 'invalid correction amount',
                    3: 'nonfinite or non-SDR RGB/inner-iris support'}
        raise ValueError('Red-eye Rust refused: ' + messages.get(code, str(code)))


def apply(rgb, weight, amount, *, cancelled=lambda: False):
    """Return independent, writable, contiguous float32 HWC encoded-sRGB RGB.

    weight is target-owned inward central-iris geometric candidate coverage,
    not a measured pupil, iris-colour detector or segmentation result produced
    here. The host validates source/target/revision/full-source geometry before
    supplying aligned RGB/support crops. It MUST NOT mutate either input during
    snapshot copying. No caller storage is mutated or retained. Private immutable
    snapshots feed the only colour core; geometry cannot be authenticated here.

    One amount in [0,1] lowers only strongly excessive R toward the source G/B
    mean; G and B remain bit-exact. Near-neutral catchlights, zero support and
    zero amount remain exact. Natural red/brown iris can be a false positive:
    this is not evidence of flash, and cannot restore lost iris texture/colour.

    Reject non-SDR/nonfinite/wrong-dtype values even with zero amount/support.
    No implicit colour transfer, dtype conversion, device move or fallback is
    performed. Failure/cancellation never returns partial output.
    """
    correction = _amount(amount)
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    if type(rgb) is not np.ndarray or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Red-eye requires an HWC float32 RGB array')
    height, width, _ = rgb.shape
    _shape(rgb, (height, width, 3), 'RGB')
    _shape(weight, (height, width), 'Inner-iris support')
    _poll(cancelled)
    _admit(width, height)
    source = _snapshot(rgb, rgb.shape, 'RGB', cancelled)
    coverage = _snapshot(weight, weight.shape, 'Inner-iris support', cancelled)
    _poll(cancelled)
    lib = native()
    output = np.empty_like(source, order='C')
    callback, errors = _callback(cancelled)
    code = lib.lrt_red_eye_apply_v1(
        source.ctypes.data_as(P), source.size,
        coverage.ctypes.data_as(P), coverage.size,
        width, height, correction,
        output.ctypes.data_as(P), output.size, callback, None,
    )
    _result(code, cancelled, errors)
    # Bounded scratch also checks an accidentally incompatible/misbehaving
    # installed core. This is not a second implementation of the colour gate.
    for index, row in enumerate(output):
        _poll(cancelled)
        if not np.isfinite(row).all() or np.any(row < 0.0) or np.any(row > 1.0):
            raise RuntimeError('Red-eye returned invalid SDR output; discarded')
        original = source[index]
        if (not np.array_equal(row[:, 1:].view(np.uint32), original[:, 1:].view(np.uint32))
                or np.any(row[:, 0] > original[:, 0])):
            raise RuntimeError('Red-eye violated the red-only correction contract; discarded')
        if correction == 0.0:
            unchanged = np.array_equal(row.view(np.uint32), original.view(np.uint32))
        else:
            outside = coverage[index] == 0.0
            unchanged = np.array_equal(row[outside].view(np.uint32), original[outside].view(np.uint32))
        if not unchanged:
            raise RuntimeError('Red-eye changed neutral or unsupported pixels; discarded')
    _poll(cancelled)
    return output
