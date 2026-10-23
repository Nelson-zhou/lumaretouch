"""Original Rust tooth colour bridge. AUTHORED / UNRUN, no acceptance claim.

One numerical implementation for NumPy and Torch hosts. Torch hosts explicitly
transfer to float32 CPU arrays before this boundary and restore their device
afterwards; this module does not import Torch or duplicate the colour operation.
No runtime build, fallback filter, download, segmentation or generated teeth.
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
    path = Path(__file__).resolve().parent / 'bin/liblrt_teeth_colour.so'
    if not path.is_file():
        raise RuntimeError('Teeth colour Rust core is not installed; no fallback was applied')
    lib = C.CDLL(str(path))
    lib.lrt_teeth_colour_abi.argtypes = []
    lib.lrt_teeth_colour_abi.restype = C.c_uint32
    if lib.lrt_teeth_colour_abi() != 1:
        raise RuntimeError('Teeth colour Rust ABI mismatch')
    lib.lrt_teeth_colour_apply_v1.argtypes = [
        P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t,
        C.c_float, C.c_float, P, C.c_size_t, CANCEL, C.c_void_p,
    ]
    lib.lrt_teeth_colour_apply_v1.restype = C.c_int
    return lib


def available():
    """Check the actual library/ABI/symbols, not merely an optimistic file flag."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Teeth colour cancelled; private output discarded')


def _amount(value, label):
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
        raise ValueError(label + ' requires exact float32 shape ' + str(shape))


def _admit(width, height):
    if (type(width) is not int or type(height) is not int
            or min(width, height) < 1 or max(width, height) > MAX_DIMENSION):
        raise ValueError('Teeth colour dimensions are outside the supported canvas range')
    pixels = width * height
    # Caller RGB/mask 16 B/px + owned snapshots 16 B/px + output 12 B/px.
    # Native code allocates nothing; validation scratch is bounded by one row.
    if pixels > MAX_PIXELS or 44 * pixels + SCRATCH_BYTES > MAX_WORKING_BYTES:
        raise MemoryError('Teeth colour exceeds its full-resolution memory budget; no proxy fallback')
    additional = 28 * pixels + SCRATCH_BYTES
    if additional > _available_estimate():
        raise MemoryError('Insufficient CPU memory for independent teeth colour snapshots')
    return additional


def _snapshot(array, shape, label, cancelled):
    _shape(array, shape, label)
    _poll(cancelled)
    # Always own the storage, even for an already contiguous/read-only input:
    # an input's owning base could otherwise change while native code reads it.
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
            # Never let Python exceptions escape a C callback. Preserve them
            # for the caller after the native operation has stopped.
            if not errors:
                errors.append(error)
            return 1
    return CANCEL(poll), errors


def _result(code, cancelled, errors):
    if errors:
        raise errors[0]
    if code == 4:
        raise InterruptedError('Teeth colour cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Teeth colour Rust resource budget exceeded')
    if code == 6:
        raise RuntimeError('Teeth colour Rust panic contained; private output discarded')
    if code:
        messages = {1: 'invalid ABI, lengths, dimensions or buffer aliasing',
                    2: 'invalid brightness/yellow amount',
                    3: 'nonfinite or non-SDR RGB/coverage'}
        raise ValueError('Teeth colour Rust refused: ' + messages.get(code, str(code)))


def apply(rgb, weight, brightness, yellow, *, cancelled=lambda: False):
    """Return an independent, contiguous float32 HWC encoded working-sRGB array.

    weight is existing source/face-owned teeth coverage, never a guessed mouth
    rectangle. The caller authenticates its source, face, revision and geometry.
    It MUST NOT mutate input storage during snapshot copying. No caller storage
    is mutated or retained. Private immutable snapshots feed the shared Rust
    implementation; on failure/cancellation no partial output is returned.

    This SDR-only boundary rejects negative, HDR, nonfinite and wrong-dtype data
    even with neutral settings or zero coverage; it never silently quantizes it.
    Output remains writable for normal host composition, but never aliases input.
    """
    bright = _amount(brightness, 'Brightness')
    remove_yellow = _amount(yellow, 'Yellow removal')
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    if type(rgb) is not np.ndarray or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('Teeth colour requires an HWC float32 RGB array')
    height, width, _ = rgb.shape
    _shape(rgb, (height, width, 3), 'RGB')
    _shape(weight, (height, width), 'Teeth coverage')
    _poll(cancelled)
    _admit(width, height)
    source = _snapshot(rgb, rgb.shape, 'RGB', cancelled)
    coverage = _snapshot(weight, weight.shape, 'Teeth coverage', cancelled)
    _poll(cancelled)
    lib = native()
    output = np.empty_like(source, order='C')
    callback, errors = _callback(cancelled)
    code = lib.lrt_teeth_colour_apply_v1(
        source.ctypes.data_as(P), source.size,
        coverage.ctypes.data_as(P), coverage.size,
        width, height, bright, remove_yellow,
        output.ctypes.data_as(P), output.size, callback, None,
    )
    _result(code, cancelled, errors)
    # Validate without a whole-image boolean temporary. Native already checks
    # results; this also refuses a corrupted/misbehaving installed library.
    for row in output:
        _poll(cancelled)
        if not np.isfinite(row).all() or np.any(row < 0.0) or np.any(row > 1.0):
            raise RuntimeError('Teeth colour returned invalid SDR output; discarded')
    _poll(cancelled)
    return output
