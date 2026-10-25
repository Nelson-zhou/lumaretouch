# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact original skin-reference Rust ABI boundary. AUTHORED / UNRUN.

Fit independent immutable real source ROIs once, then apply to CURRENT pixels.
No Python effect implementation, native build/download, RGB8 conversion, source
replay or ownership inference. Same-photo identity and reference-face exclusion
are mandatory HOST responsibilities, not certificates carried by MeasuredFit.
"""
import ctypes as C
from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path

import numpy as np

from .cpu_memory_budget import available_estimate as _available_estimate

ENCODING = 'encoded-working-srgb-d65-sdr'
ABI_VERSION = 1
TRANSFORM_LEN = 4
DIAGNOSTICS_LEN = 24
MAX_DIMENSION = 65_536
MAX_FIT_PIXELS = 32_000_000
MAX_APPLY_PIXELS = 1_048_576
MAX_FRAME_PIXELS = 32_000_000
MAX_LOG_LUMINANCE = math.log(2.0)
MAX_LOG_CHROMA = .35
MAX_FIT_BYTES = 2 * 1024**3
MAX_APPLY_BYTES = 64 * 1024**2
MAX_WORKING_BYTES = 2 * 1024**3
FIT_FIXED_SCRATCH_BYTES = 262_144
APPLY_FIXED_SCRATCH_BYTES = 4096
SCRATCH_BYTES = 8 * 1024**2
COPY_PIXELS = 4096
P = C.POINTER(C.c_float)
D = C.POINTER(C.c_double)
CANCEL = C.CFUNCTYPE(C.c_int32, C.c_void_p)


@lru_cache(maxsize=1)
def native():
    """Load only the packaged original core; missing ABI is never a fallback."""
    path = Path(__file__).resolve().parent / 'bin/liblrt_skin_reference_match.so'
    if not path.is_file():
        raise RuntimeError('Skin reference match Rust core is not installed; no fallback was applied')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_skin_reference_match_abi.argtypes = []
        lib.lrt_skin_reference_match_abi.restype = C.c_uint32
        if lib.lrt_skin_reference_match_abi() != ABI_VERSION:
            raise RuntimeError('Skin reference match Rust ABI mismatch; no fallback was applied')
        lib.lrt_skin_reference_match_fit_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t,
            P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t,
            D, C.c_size_t, D, C.c_size_t, D, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_skin_reference_match_fit_v1.restype = C.c_int32
        lib.lrt_skin_reference_match_apply_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t, C.c_size_t, C.c_size_t,
            D, C.c_size_t, C.c_float, P, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_skin_reference_match_apply_v1.restype = C.c_int32
    except (OSError, AttributeError) as error:
        raise RuntimeError('Skin reference match required native ABI cannot load; no fallback was applied') from error
    return lib


def available():
    """Symbols/ABI only: not authenticated evidence, packaging or photo quality."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def _number(value, label):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError(label + ' requires a finite number')
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(label + ' requires a finite number') from error
    if not math.isfinite(result):
        raise ValueError(label + ' requires a finite number')
    return result


def _limits(value):
    if type(value) not in (tuple, list) or len(value) != 2:
        raise ValueError('Skin reference limits require [maximum log luminance, maximum log chroma]')
    result = tuple(_number(v, 'Skin reference limit') for v in value)
    if not 0 <= result[0] <= MAX_LOG_LUMINANCE or not 0 <= result[1] <= MAX_LOG_CHROMA:
        raise ValueError('Skin reference limits exceed ln(2) brightness or 0.35 chroma')
    return result


def _pixels(shape, label):
    if type(shape) not in (tuple, list) or len(shape) != 2:
        raise ValueError(label + ' requires exact (height,width)')
    height, width = shape
    if (type(height) is not int or type(width) is not int
            or min(height, width) < 1 or max(height, width) > MAX_DIMENSION):
        raise ValueError(label + ' dimensions are outside 1..65536')
    return height * width


def memory_estimate(reference_shape, target_shape):
    """Pure additional fit bytes; independent grids, no allocation/live probe.

    Caller RGB+coverage16 N + private snapshots16 N + native256KiB + 8MiB
    bounded validation/allocator allowance. The allowance also covers the tiny
    f64 limits/outputs. The core's own16 N budget alone omits our copies.
    """
    count = (_pixels(reference_shape, 'Reference source')
             + _pixels(target_shape, 'Target source'))
    native_bytes = 16 * count + FIT_FIXED_SCRATCH_BYTES
    additional = native_bytes + SCRATCH_BYTES
    if (count > MAX_FIT_PIXELS or native_bytes > MAX_FIT_BYTES
            or 16 * count + additional > MAX_WORKING_BYTES):
        raise MemoryError('Skin reference fit exceeds combined source memory/pixel budget; no proxy fallback')
    return additional


def _tile_rows(shape, *, tiled, tile_rows):
    count = _pixels(shape, 'Current RGB')
    height, width = shape
    if type(tiled) is not bool:
        raise ValueError('tiled must be a boolean')
    if count > (MAX_FRAME_PIXELS if tiled else MAX_APPLY_PIXELS):
        raise MemoryError('Skin reference current image exceeds admitted frame/tile pixel budget')
    if not tiled and tile_rows is not None:
        raise ValueError('tile_rows is only supported for tiled application')
    maximum_rows = max(1, MAX_APPLY_PIXELS // width)
    if tile_rows is not None and (type(tile_rows) is not int or not 1 <= tile_rows <= maximum_rows):
        raise ValueError('tile_rows must be a positive integer within the native tile pixel limit')
    return min(height, maximum_rows if tile_rows is None else tile_rows)


def application_memory_estimate(shape, *, tiled=False, tile_rows=None, neutral=False):
    """Pure additional bytes for one tile or private full-frame row-strip apply.

    Active: full snapshots16 N + full output12 N + native stage12 T +4KiB
    +8MiB allowance. Caller RGB/coverage add16 N to the hard total ceiling.
    Contiguous row strips borrow the private snapshots/output; no duplicate tile
    copies. Neutral: snapshots16 N (current snapshot is returned) +8MiB. Coverage
    is conservatively charged even when absent. No live probe/native loading.
    """
    if type(neutral) is not bool:
        raise ValueError('neutral must be a boolean')
    rows = _tile_rows(shape, tiled=tiled, tile_rows=tile_rows)
    count = shape[0] * shape[1]
    tile_count = rows * shape[1]
    if 40 * tile_count + APPLY_FIXED_SCRATCH_BYTES > MAX_APPLY_BYTES:
        raise MemoryError('Skin reference native tile memory budget exceeded')
    additional = (16 * count + SCRATCH_BYTES if neutral else
                  28 * count + 12 * tile_count + APPLY_FIXED_SCRATCH_BYTES + SCRATCH_BYTES)
    if 16 * count + additional > MAX_WORKING_BYTES:
        raise MemoryError('Skin reference application exceeds full snapshot/output memory budget')
    return additional


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Skin reference match cancelled; private output discarded')


def _admit(estimate, byte_budget, cancelled):
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    _poll(cancelled)
    if byte_budget is not None and (type(byte_budget) is not int or byte_budget < 0):
        raise ValueError('byte_budget must be a nonnegative integer of additional available bytes')
    if byte_budget is not None and estimate > byte_budget:
        raise MemoryError('Skin reference match exceeds the host additional-memory allowance')
    if estimate > _available_estimate():
        raise MemoryError('Insufficient CPU memory for skin reference snapshots, output and native scratch')


def _shape(value, shape, label):
    if type(value) is not np.ndarray or value.dtype != np.float32 or value.shape != shape:
        raise ValueError(label + ' requires exact native float32 shape ' + str(shape))


def _rgb_shape(value, label):
    if type(value) is not np.ndarray or value.ndim != 3 or value.shape[2] != 3:
        raise ValueError(label + ' requires HWC3 native float32 RGB')
    _shape(value, value.shape, label)
    _pixels(value.shape[:2], label)
    return value.shape[:2]


def _blocks(shape):
    for row in range(shape[0]):
        for left in range(0, shape[1], COPY_PIXELS):
            yield row, slice(left, min(left + COPY_PIXELS, shape[1]))


def _valid_sdr(block):
    return np.isfinite(block).all() and not np.any(block < 0.0) and not np.any(block > 1.0)


def _snapshot(value, shape, label, cancelled):
    _shape(value, shape, label)
    _poll(cancelled)
    result = np.empty(shape, dtype=np.float32, order='C')
    for row, columns in _blocks(shape):
        _poll(cancelled)
        block = result[row, columns]
        block[...] = value[row, columns]
        if not _valid_sdr(block):
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
        raise InterruptedError('Skin reference match cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Skin reference match Rust resource admission/allocation refused')
    if code == 6:
        raise RuntimeError('Skin reference match Rust panic contained; private output discarded')
    if code:
        messages = {1: 'ABI/length/dimension/overlap mismatch', 2: 'invalid settings',
                    3: 'invalid pixels or numerical refusal',
                    7: 'insufficient reliable selected-reference evidence',
                    8: 'insufficient reliable independent-target evidence',
                    9: 'excessive dispersion or insufficient retained evidence',
                    10: 'invalid transform'}
        raise ValueError('Skin reference match Rust refused: ' + messages.get(code, str(code)))


@dataclass(frozen=True)
class MeasuredFit:
    """Immutable numerical result, NOT an ownership, source or review token.

    Fields contain only Python scalar tuples, never writable NumPy/native views.
    The host must bind a result to authenticated source and reviewed supports.
    """
    reference_shape: tuple
    target_shape: tuple
    limits: tuple
    transform: tuple
    diagnostics: tuple

    def checked(self):
        for value in (self.reference_shape, self.target_shape, self.limits,
                      self.transform, self.diagnostics):
            if type(value) is not tuple:
                raise ValueError('Skin reference measured fit requires immutable scalar tuples')
        memory_estimate(self.reference_shape, self.target_shape)
        limits = _limits(self.limits)
        if len(self.transform) != TRANSFORM_LEN or len(self.diagnostics) != DIAGNOSTICS_LEN:
            raise ValueError('Skin reference measured fit has invalid ABI lengths')
        transform = tuple(_number(v, 'Measured transform') for v in self.transform)
        diagnostics = tuple(_number(v, 'Measured diagnostics') for v in self.diagnostics)
        if (transform[0] != ABI_VERSION or abs(transform[1]) > limits[0] + 1e-12
                or math.hypot(transform[2], transform[3]) > limits[1] + 1e-12):
            raise ValueError('Skin reference measured transform is invalid or exceeds its limits')
        if diagnostics[0] != ABI_VERSION:
            raise ValueError('Skin reference measured diagnostics ABI mismatch')
        for offset, shape in ((0, self.reference_shape), (1, self.target_shape)):
            count, weight, effective = (diagnostics[1 + offset], diagnostics[3 + offset],
                                        diagnostics[5 + offset])
            # Long streaming f64 sums can put W*W/Q slightly above count. This
            # structural upper guard must not assume exact real arithmetic.
            roundoff = max(1e-7, count * 1e-6)
            if (count != math.floor(count) or not 64 <= count <= shape[0] * shape[1]
                    or not 64 <= weight <= count + roundoff
                    or not 64 <= effective <= count + roundoff):
                raise ValueError('Skin reference measured diagnostics lack reliable evidence')
        for start in (13, 16):
            mad = diagnostics[start:start + 3]
            if min(mad) < 0 or mad[0] > .50 + 1e-12 or math.hypot(*mad[1:]) > .30 + 1e-12:
                raise ValueError('Skin reference measured dispersion exceeds the core contract')
        flags = diagnostics[22]
        if flags != math.floor(flags) or not 0 <= flags <= 7 or not .5 <= diagnostics[23] <= 1 + 1e-6:
            raise ValueError('Skin reference measured flags/retained evidence are invalid')
        if any(abs(diagnostics[19 + i] - (diagnostics[7 + i] - diagnostics[10 + i])) > 1e-12
               for i in range(3)):
            raise ValueError('Skin reference measured raw shifts disagree with source centres')
        return self


def fit(reference_rgb, reference_coverage, target_rgb, target_coverage, *,
        limits=(MAX_LOG_LUMINANCE, MAX_LOG_CHROMA), byte_budget=None,
        cancelled=lambda: False):
    """Fit whole reviewed independent source ROIs, not source/current tile pairs.

    Even zero limits require actual reliable evidence from BOTH populations.
    Strided native float32 inputs are snapshotted without resizing. The caller
    must keep inputs immutable while copied. No source array is mutated. Output
    tuple diagnostics follow the exact 24-double layout in the original header.
    """
    limits = _limits(limits)
    reference_shape = _rgb_shape(reference_rgb, 'Reference source RGB')
    target_shape = _rgb_shape(target_rgb, 'Target source RGB')
    _shape(reference_coverage, reference_shape, 'Reference skin coverage')
    _shape(target_coverage, target_shape, 'Target skin coverage')
    _admit(memory_estimate(reference_shape, target_shape), byte_budget, cancelled)
    reference = _snapshot(reference_rgb, reference_rgb.shape, 'Reference source RGB', cancelled)
    reference_weight = _snapshot(reference_coverage, reference_shape, 'Reference skin coverage', cancelled)
    target = _snapshot(target_rgb, target_rgb.shape, 'Target source RGB', cancelled)
    target_weight = _snapshot(target_coverage, target_shape, 'Target skin coverage', cancelled)
    lib = native()
    _poll(cancelled)
    bound = (C.c_double * 2)(*limits)
    transform = (C.c_double * TRANSFORM_LEN)(*[math.nan] * TRANSFORM_LEN)
    diagnostics = (C.c_double * DIAGNOSTICS_LEN)(*[math.nan] * DIAGNOSTICS_LEN)
    callback, errors = _callback(cancelled)
    code = lib.lrt_skin_reference_match_fit_v1(
        reference.ctypes.data_as(P), reference.size, reference_weight.ctypes.data_as(P), reference_weight.size,
        reference_shape[1], reference_shape[0], target.ctypes.data_as(P), target.size,
        target_weight.ctypes.data_as(P), target_weight.size, target_shape[1], target_shape[0],
        bound, 2, transform, TRANSFORM_LEN, diagnostics, DIAGNOSTICS_LEN, callback, None,
    )
    _result(code, cancelled, errors)
    try:
        result = MeasuredFit(tuple(reference_shape), tuple(target_shape), limits,
                             tuple(transform), tuple(diagnostics)).checked()
    except ValueError as error:
        raise RuntimeError('Skin reference match returned invalid fit/diagnostics; discarded') from error
    _poll(cancelled)
    return result


def _validate_output(current, coverage, output, transform, cancelled):
    zero_shift = all(v == 0.0 for v in transform[1:])
    for row, columns in _blocks(output.shape):
        _poll(cancelled)
        before, after = current[row, columns], output[row, columns]
        if not _valid_sdr(after):
            raise RuntimeError('Skin reference match returned invalid SDR pixels; discarded')
        protected = ((coverage[row, columns] == 0.0)
                     | np.all(before == 0.0, axis=-1) | np.all(before == 1.0, axis=-1))
        if zero_shift:
            protected = np.ones_like(protected, dtype=bool)
        if not np.array_equal(before.view(np.uint32)[protected], after.view(np.uint32)[protected]):
            raise RuntimeError('Skin reference match changed exact protected/neutral pixels; discarded')


def _apply(current_rgb, coverage, measured_fit, amount, *, tiled, tile_rows,
           byte_budget, cancelled):
    amount = _number(amount, 'Skin reference amount')
    if not 0 <= amount <= 1:
        raise ValueError('Skin reference amount must be in [0,1]')
    shape = _rgb_shape(current_rgb, 'Current RGB')
    if coverage is not None:
        _shape(coverage, shape, 'Current reviewed coverage')
    if measured_fit is not None:
        if type(measured_fit) is not MeasuredFit:
            raise ValueError('Skin reference application requires a MeasuredFit, not an arbitrary transform')
        measured_fit.checked()
    if amount != 0.0 and (coverage is None or measured_fit is None):
        raise ValueError('Active skin reference application requires reviewed coverage and a measured fit')
    rows = _tile_rows(shape, tiled=tiled, tile_rows=tile_rows)
    estimate = application_memory_estimate(shape, tiled=tiled, tile_rows=tile_rows, neutral=amount == 0.0)
    _admit(estimate, byte_budget, cancelled)
    current = _snapshot(current_rgb, current_rgb.shape, 'Current RGB', cancelled)
    weight = None if coverage is None else _snapshot(coverage, shape, 'Current reviewed coverage', cancelled)
    # Exact neutral copy is an identity path, not an alternative effect algorithm.
    # Supplied coverage/fit still validate, but neither evidence nor core is needed.
    if amount == 0.0:
        _poll(cancelled)
        current.setflags(write=True)
        return current
    lib = native()
    _poll(cancelled)
    transform = (C.c_double * TRANSFORM_LEN)(*measured_fit.transform)
    output = np.empty(current.shape, dtype=np.float32, order='C')
    callback, errors = _callback(cancelled)
    for top in range(0, shape[0], rows):
        _poll(cancelled)
        tile = current[top:top + rows]
        tile_weight = weight[top:top + rows]
        tile_output = output[top:top + rows]
        code = lib.lrt_skin_reference_match_apply_v1(
            tile.ctypes.data_as(P), tile.size, tile_weight.ctypes.data_as(P), tile_weight.size,
            shape[1], tile.shape[0], transform, TRANSFORM_LEN, amount,
            tile_output.ctypes.data_as(P), tile_output.size, callback, None,
        )
        _result(code, cancelled, errors)
        _validate_output(tile, tile_weight, tile_output, measured_fit.transform, cancelled)
    _poll(cancelled)
    return output


def apply(current_rgb, coverage=None, measured_fit=None, amount=0.0, *,
          byte_budget=None, cancelled=lambda: False):
    """Apply one <=1,048,576-pixel CURRENT tile; preserve original dimensions.

    No native origin is passed: source-grid registration/permission belongs to
    the host. Fit source dimensions need not equal tile dimensions. Owned result
    only; no partial publication. At neutral, validate/copy current exact bits
    without loading the core, even when evidence is absent.
    """
    return _apply(current_rgb, coverage, measured_fit, amount, tiled=False,
                  tile_rows=None, byte_budget=byte_budget, cancelled=cancelled)


def apply_tiled(current_rgb, coverage=None, measured_fit=None, amount=0.0, *,
                tile_rows=None, byte_budget=None, cancelled=lambda: False):
    """Apply one unchanged fit across contiguous full-width row strips privately.

    Snapshot the full current frame/support before any call; return a whole owned
    frame only after every strip succeeds. A failed/cancelled later strip cannot
    publish earlier strips. No per-tile fitting, halo, geometry or quantization.
    Multiple targets still need a HOST-owned frame transaction and exclusion.
    tile_rows optionally chooses a positive strip height within the ABI budget.
    """
    return _apply(current_rgb, coverage, measured_fit, amount, tiled=True,
                  tile_rows=tile_rows, byte_budget=byte_budget, cancelled=cancelled)
