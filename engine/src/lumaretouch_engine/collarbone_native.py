# SPDX-License-Identifier: GPL-3.0-or-later
"""Original manually reviewed observed-source 2D collarbone core. AUTHORED / UNRUN.

No AI3D, missing-ridge synthesis, anatomy detector, native build or Python image
algorithm fallback. Evidence is prepared once from genuine source pixels; Rust
composes its signed scalar field onto CURRENT-stage RGB, including tiled paths.
"""
import ctypes as C
from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path

import numpy as np

from .cpu_memory_budget import available_estimate as _available_estimate

MAX_PIXELS = 32_000_000
MAX_DIMENSION = 65_536
MAX_LOG_GAIN = 0.12
FIELD_TOLERANCE = 1e-8
MIN_HALF_WIDTH = 4.0
MAX_HALF_WIDTH = 256.0
NATIVE_SCRATCH_BYTES_PER_PIXEL = 32
MAX_WORKING_BYTES = 4 * 1024**3
SCRATCH_BYTES = 8 * 1024**2
COPY_PIXELS = 4096
ENCODING = 'encoded-working-srgb-d65-sdr'
P = C.POINTER(C.c_float)
DP = C.POINTER(C.c_double)
UP = C.POINTER(C.c_uint32)
SP = C.POINTER(C.c_uint64)
CANCEL = C.CFUNCTYPE(C.c_int, C.c_void_p)
STATS = ('reviewed_band_pixels', 'covered_band_pixels', 'border_refused_pixels',
         'unsupported_sample_pixels', 'unreliable_source_pixels',
         'insufficient_signal_pixels', 'supported_pixels', 'overlap_pixels')


@dataclass(frozen=True)
class PreparedCollarbone:
    """Transient, source-grid-owned evidence, never portable preset/recipe data.

    The host owns source/revision/person/transform/manual-review authentication.
    This value is not cryptographic provenance and must not be reused after any
    change to those identities. field is a read-only owned float32 ROI, not RGB.
    """
    field: np.ndarray
    origin: tuple
    source_shape: tuple
    report: object


@lru_cache(maxsize=1)
def native():
    path = Path(__file__).resolve().parent / 'bin/liblrt_collarbone.so'
    if not path.is_file():
        raise RuntimeError('Collarbone Rust core is not installed; no fallback was applied')
    try:
        lib = C.CDLL(str(path))
        lib.lrt_collarbone_abi.argtypes = []
        lib.lrt_collarbone_abi.restype = C.c_uint32
        if lib.lrt_collarbone_abi() != 1:
            raise RuntimeError('Collarbone Rust ABI mismatch')
        lib.lrt_collarbone_prepare_v1.argtypes = [
            P, C.c_size_t, P, C.c_size_t,
            C.c_size_t, C.c_size_t, C.c_size_t, C.c_size_t, C.c_size_t, C.c_size_t,
            DP, C.c_size_t, UP, C.c_size_t, DP, C.c_size_t,
            C.c_size_t, C.c_size_t, C.c_size_t, C.c_size_t,
            P, C.c_size_t, SP, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_collarbone_prepare_v1.restype = C.c_int
        lib.lrt_collarbone_compose_v1.argtypes = [
            P, C.c_size_t, C.c_size_t, C.c_size_t, C.c_size_t, C.c_size_t,
            P, C.c_size_t, C.c_size_t, C.c_size_t, C.c_size_t, C.c_size_t,
            C.c_size_t, C.c_size_t, C.c_float, P, C.c_size_t, CANCEL, C.c_void_p,
        ]
        lib.lrt_collarbone_compose_v1.restype = C.c_int
    except (OSError, AttributeError) as error:
        raise RuntimeError('Collarbone Rust core cannot load its required ABI') from error
    return lib


def available():
    """Symbol/ABI readiness only, not photographic or anatomical availability."""
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False


def _shape_pair(shape):
    if type(shape) not in (tuple, list) or len(shape) != 2:
        raise ValueError('Collarbone requires exact (height,width) dimensions')
    h, w = shape
    if type(h) is not int or type(w) is not int or min(h, w) < 1 or max(h, w) > MAX_DIMENSION:
        raise ValueError('Collarbone dimensions are outside the supported range')
    if h*w > MAX_PIXELS:
        raise MemoryError('Collarbone exceeds its source pixel budget; no proxy fallback')
    return h, w


def _number(value, low, high, label):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))):
        raise ValueError(label + ' requires a finite number')
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(label + ' requires a finite number') from error
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(label + ' is outside its supported range')
    return result


def _curves(curves, shape):
    h, w = _shape_pair(shape)
    if type(curves) not in (tuple, list) or not 1 <= len(curves) <= 2:
        raise ValueError('Collarbone requires one or two independently reviewed traces')
    result, ids = [], set()
    for curve in curves:
        if type(curve) is not dict or set(curve) != {'id', 'points', 'width'}:
            raise ValueError('Collarbone trace requires exactly id, points and width')
        if curve['id'] not in ('left', 'right') or curve['id'] in ids:
            raise ValueError('Collarbone trace ids must be unique reviewed screen sides')
        ids.add(curve['id'])
        points = curve['points']
        if type(points) not in (tuple, list) or not 3 <= len(points) <= 8:
            raise ValueError('Each collarbone trace requires three to eight points')
        vertices = []
        for p in points:
            if type(p) not in (tuple, list) or len(p) != 2:
                raise ValueError('Collarbone points require exact normalized xy pairs')
            x = _number(p[0], 0.0, 1.0, 'Collarbone x')
            y = _number(p[1], 0.0, 1.0, 'Collarbone y')
            if not 0.0 < x < 1.0 or not 0.0 < y < 1.0:
                raise ValueError('Collarbone trace points must lie strictly within the source')
            vertices.append((x, y))
        width = _number(curve['width'], 0.0, 1.0, 'Collarbone half-width')
        if not MIN_HALF_WIDTH <= width*min(h, w) <= MAX_HALF_WIDTH:
            raise ValueError('Collarbone half-width must be 4..256 pixels on this genuine source grid; no scale clamp')
        result.append({'id': curve['id'], 'points': tuple(vertices), 'width': width})
    # Stable screen-side order removes caller-list ordering from overlap tie breaks.
    return tuple(sorted(result, key=lambda value: value['id']))


def _layout(shape, curves):
    h, w = _shape_pair(shape)
    checked = _curves(curves, (h, w))
    points = [(x*w-0.5, y*h-0.5, curve['width']*min(h, w))
              for curve in checked for x, y in curve['points']]
    left = max(0, math.floor(min(x-r for x, _, r in points)))
    top = max(0, math.floor(min(y-r for _, y, r in points)))
    right = min(w, math.ceil(max(x+r for x, _, r in points))+1)
    bottom = min(h, math.ceil(max(y+r for _, y, r in points))+1)
    # A real source window, including every possible normal direction, full narrow
    # filter window and bilinear corner. Clip only to true source boundaries.
    halo = max(math.ceil(2*r + max(1, math.floor(r/4)) + 2) for _, _, r in points)
    sample = (max(0, left-halo), max(0, top-halo), min(w, right+halo), min(h, bottom+halo))
    return checked, (left, top, right, bottom), sample


def memory_estimate(shape, curves=None):
    """Pure additional preparation bytes, no allocation/native load/cgroup read.

    With curves, charge only the real evidence window and trace-band output ROI:
    16 B/sample pixel snapshots + 32 B/sample pixel peak Rust scratch + 4 B/field
    pixel, plus 8 MiB allowance. Caller full-source RGB/coverage already exist and
    are not duplicated. Their 16 B/source pixel is INCLUDED in the 4 GiB absolute
    admission, but not the returned additional bytes. The host must separately
    charge any coverage raster it has not created yet and its other render data.
    """
    h, w = _shape_pair(shape)
    if curves is None:
        sample_pixels = field_pixels = h*w
    else:
        _, output, sample = _layout((h, w), curves)
        sample_pixels = (sample[2]-sample[0])*(sample[3]-sample[1])
        field_pixels = (output[2]-output[0])*(output[3]-output[1])
    additional = 48*sample_pixels + 4*field_pixels + SCRATCH_BYTES
    if 16*h*w + additional > MAX_WORKING_BYTES:
        raise MemoryError('Collarbone exceeds its full-source plus real-ROI CPU budget; no proxy fallback')
    return additional


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Collarbone cancelled; private output discarded')


def _array(array, shape, label):
    if type(array) is not np.ndarray or array.dtype != np.float32 or array.shape != shape:
        raise ValueError(label + ' requires exact native float32 shape ' + str(shape))


def _blocks(shape):
    for row in range(shape[0]):
        for left in range(0, shape[1], COPY_PIXELS):
            yield row, slice(left, min(left+COPY_PIXELS, shape[1]))


def _snapshot(array, label, cancelled, *, field=False):
    _poll(cancelled)
    result = np.empty(array.shape, dtype=np.float32, order='C')
    bound = MAX_LOG_GAIN+FIELD_TOLERANCE if field else 1.0
    low = -bound if field else 0.0
    for row, columns in _blocks(array.shape):
        _poll(cancelled)
        block = result[row, columns]
        block[...] = array[row, columns]
        if not np.isfinite(block).all() or np.any(block < low) or np.any(block > bound):
            raise ValueError(label + (' requires a finite bounded signed log-gain field' if field
                                     else ' requires finite SDR [0,1] values; no clipping'))
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
        raise InterruptedError('Collarbone cancelled; private output discarded')
    _poll(cancelled)
    if code == 5:
        raise MemoryError('Collarbone Rust resource budget exceeded')
    if code == 6:
        raise RuntimeError('Collarbone Rust panic contained; private output discarded')
    if code:
        meanings = {1: 'invalid ABI, lengths, dimensions or buffer aliasing',
                    2: 'invalid amount or unsupported/degenerate/crossing reviewed trace geometry',
                    3: 'invalid RGB/coverage/field or numerical refusal'}
        raise ValueError('Collarbone Rust refused: ' + meanings.get(code, str(code)))


def _report(values):
    result = dict(zip(STATS, (int(v) for v in values)))
    supported = result['supported_pixels']
    refused = sum(result[name] for name in STATS[2:6])
    if supported:
        status = 'partially_supported' if refused else 'supported'
    elif not result['reviewed_band_pixels']:
        status = 'no_reviewed_band'
    elif not result['covered_band_pixels']:
        status = 'no_owned_coverage'
    elif result['border_refused_pixels'] == result['covered_band_pixels']:
        status = 'unsupported_source_border'
    elif result['unsupported_sample_pixels'] + result['border_refused_pixels'] == result['covered_band_pixels']:
        status = 'unsupported_source_support'
    elif result['unreliable_source_pixels']:
        status = 'unreliable_source'
    else:
        status = 'no_observed_signal'
    result['status'] = status
    result['admitted_pixels'] = supported
    return result


def prepare(reference_rgb, coverage, curves, *, cancelled=lambda: False):
    """Measure immutable effective-source evidence, never an edited preview proxy.

    RGB is exact native float32 encoded-working-sRGB-D65 SDR HWC. Coverage is exact
    float32 HW permission from this person's semantic body skin INTERSECTED with
    reviewed manual support/exclusions. That coverage must include genuine near
    AND farther baseline pixels, not just a narrow painted line. Every sampled
    neighborhood excludes coverage-zero pixels; no unsupported pixels fill holes.

    Curves are 1..2 exact {id,points,width}, id image/screen left/right (not gender
    or anatomical inference). Points are source edge-normalized: x*W-.5,y*H-.5.
    Width is a band HALF-WIDTH/min(H,W), admitted 4..256 source pixels. Eligibility,
    visibility, owner/source revision and review are verified by the host, never
    inferred here. Invalid traces refuse in Rust. No absent side is generated.

    Only the real trace/halo window is snapshotted and numerically inspected;
    unused source pixels are not read. The caller must not mutate source, coverage
    or geometry during snapshots. Borders and insufficient signal return a zero
    or partially supported field with explicit counters, not a fabricated ridge.
    """
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    if type(reference_rgb) is not np.ndarray or reference_rgb.ndim != 3 or reference_rgb.shape[2] != 3:
        raise ValueError('Collarbone requires an HWC float32 original reference RGB array')
    h, w, _ = reference_rgb.shape
    _array(reference_rgb, (h, w, 3), 'Original reference RGB')
    _array(coverage, (h, w), 'Owned reviewed body coverage')
    checked, output, sample = _layout((h, w), curves)
    _poll(cancelled)
    if memory_estimate((h, w), checked) > _available_estimate():
        raise MemoryError('Insufficient CPU memory for collarbone real-source ROI snapshots and native scratch')
    sx, sy, sr, sb = sample
    ox, oy, right, bottom = output
    reference = _snapshot(reference_rgb[sy:sb, sx:sr], 'Original reference ROI', cancelled)
    weight = _snapshot(coverage[sy:sb, sx:sr], 'Owned reviewed body coverage ROI', cancelled)
    points = np.asarray([value for curve in checked for point in curve['points'] for value in point], dtype=np.float64)
    counts = np.asarray([len(curve['points']) for curve in checked], dtype=np.uint32)
    widths = np.asarray([curve['width'] for curve in checked], dtype=np.float64)
    _poll(cancelled)
    lib = native()
    _poll(cancelled)
    field = np.empty((bottom-oy, right-ox), dtype=np.float32, order='C')
    stats = np.zeros(len(STATS), dtype=np.uint64)
    callback, errors = _callback(cancelled)
    code = lib.lrt_collarbone_prepare_v1(
        reference.ctypes.data_as(P), reference.size, weight.ctypes.data_as(P), weight.size,
        w, h, sx, sy, sr-sx, sb-sy,
        points.ctypes.data_as(DP), points.size, counts.ctypes.data_as(UP), counts.size,
        widths.ctypes.data_as(DP), widths.size, ox, oy, right-ox, bottom-oy,
        field.ctypes.data_as(P), field.size, stats.ctypes.data_as(SP), stats.size, callback, None)
    _result(code, cancelled, errors)
    for row, columns in _blocks(field.shape):
        _poll(cancelled)
        block = field[row, columns]
        permission = weight[row+oy-sy, columns.start+ox-sx:columns.stop+ox-sx]
        if (not np.isfinite(block).all() or np.any(np.abs(block) > MAX_LOG_GAIN+FIELD_TOLERANCE)
                or np.any(block[permission == 0.0] != 0.0)):
            raise RuntimeError('Collarbone returned invalid or unowned evidence; discarded')
    if int(stats[6]) != int(np.count_nonzero(field)) or int(stats[0]) > field.size:
        raise RuntimeError('Collarbone returned inconsistent evidence diagnostics; discarded')
    field.setflags(write=False)
    _poll(cancelled)
    return PreparedCollarbone(field, (ox, oy), (h, w), _report(stats))


def _origin(value, shape, source_shape, label):
    if type(value) not in (tuple, list) or len(value) != 2 or any(type(v) is not int or v < 0 for v in value):
        raise ValueError(label + ' requires exact nonnegative integer (x,y)')
    x, y = value
    if x+shape[1] > source_shape[1] or y+shape[0] > source_shape[0]:
        raise ValueError(label + ' extends outside the genuine source grid')
    return x, y


def compose_field(current_rgb, field, amount, *, field_origin, source_shape,
                  origin=(0, 0), cancelled=lambda: False):
    """Apply an already prepared ROI, or a crop of it, to CURRENT-stage RGB.

    current and field may have independent source-grid origins. Outside the field
    is exact zero. Both must share the host-authenticated immutable source identity.
    Cropping prepared evidence is allowed; re-measuring from tiles is not. The
    budget charges only supplied current/field pixels, not full-source scratch.
    Current pure black/white, amount zero and field zero remain bit-exact copies.
    """
    amount = _number(amount, 0.0, 1.0, 'Collarbone amount')
    if not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    source_shape = _shape_pair(source_shape)
    if type(current_rgb) is not np.ndarray or current_rgb.ndim != 3 or current_rgb.shape[2] != 3:
        raise ValueError('Collarbone composition requires HWC float32 current RGB')
    h, w, _ = current_rgb.shape
    _shape_pair((h, w))
    _array(current_rgb, (h, w, 3), 'Current RGB')
    if type(field) is not np.ndarray or field.ndim != 2:
        raise ValueError('Collarbone field requires an HW float32 array')
    _shape_pair(field.shape)
    _array(field, field.shape, 'Prepared log-gain field')
    x, y = _origin(origin, (h, w), source_shape, 'Current tile origin')
    fx, fy = _origin(field_origin, field.shape, source_shape, 'Prepared field origin')
    additional = 24*h*w + 4*field.size + SCRATCH_BYTES
    if 36*h*w + 8*field.size + SCRATCH_BYTES > MAX_WORKING_BYTES:
        raise MemoryError('Collarbone current-stage composition exceeds its CPU budget')
    _poll(cancelled)
    if additional > _available_estimate():
        raise MemoryError('Insufficient CPU memory for collarbone current-stage composition')
    current = _snapshot(current_rgb, 'Current RGB', cancelled)
    prepared = _snapshot(field, 'Prepared log-gain field', cancelled, field=True)
    _poll(cancelled)
    lib = native()
    _poll(cancelled)
    output = np.empty_like(current, order='C')
    callback, errors = _callback(cancelled)
    code = lib.lrt_collarbone_compose_v1(
        current.ctypes.data_as(P), current.size, x, y, w, h,
        prepared.ctypes.data_as(P), prepared.size, fx, fy, prepared.shape[1], prepared.shape[0],
        source_shape[1], source_shape[0], amount, output.ctypes.data_as(P), output.size, callback, None)
    _result(code, cancelled, errors)
    for row, columns in _blocks(output.shape):
        _poll(cancelled)
        block, original = output[row, columns], current[row, columns]
        if not np.isfinite(block).all() or np.any(block < 0.0) or np.any(block > 1.0):
            raise RuntimeError('Collarbone returned invalid SDR output; discarded')
        if amount == 0.0:
            protected = np.ones(block.shape[0], dtype=bool)
        else:
            active = np.zeros(block.shape[0], dtype=bool)
            global_y = y+row
            left = max(x+columns.start, fx)
            right = min(x+columns.stop, fx+prepared.shape[1])
            if fy <= global_y < fy+prepared.shape[0] and left < right:
                active[left-x-columns.start:right-x-columns.start] = prepared[global_y-fy, left-fx:right-fx] != 0.0
            protected = ~active | np.all(original == 0.0, axis=-1) | np.all(original == 1.0, axis=-1)
        if not np.array_equal(block[protected].view(np.uint32), original[protected].view(np.uint32)):
            raise RuntimeError('Collarbone changed neutral/protected pixels; discarded')
    _poll(cancelled)
    return output


def compose(current_rgb, prepared, amount, *, origin=(0, 0), cancelled=lambda: False):
    if type(prepared) is not PreparedCollarbone:
        raise ValueError('Collarbone composition requires prepared source evidence')
    return compose_field(current_rgb, prepared.field, amount, field_origin=prepared.origin,
                         source_shape=prepared.source_shape, origin=origin, cancelled=cancelled)


def apply(current_rgb, coverage, amount, *, reference_rgb, curves, cancelled=lambda: False):
    """Full-source convenience only; integrations should retain prepare/compose split."""
    prepared = prepare(reference_rgb, coverage, curves, cancelled=cancelled)
    if type(current_rgb) is not np.ndarray or current_rgb.shape != reference_rgb.shape:
        raise ValueError('Collarbone full-source current/reference grid mismatch')
    return compose(current_rgb, prepared, amount, cancelled=cancelled)
