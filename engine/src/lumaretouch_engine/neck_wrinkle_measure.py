# SPDX-License-Identifier: GPL-3.0-or-later
"""Original checked integration for an AGPL-3.0-only numerical derivative.

AUTHORED / UNRUN. Full source-grid inputs only; this adapter cannot authenticate
source identity or neck/person ownership. The canonical resolver and support
owner must do so. No file loads, inference, graph writes or numerical fallback.
"""
from dataclasses import dataclass
import json
import math

import numpy as np

from .cpu_memory_budget import available_estimate as _available_estimate
from . import neck_wrinkle_native as _native
from .neck_wrinkle_native import (
    ABI, NeckWrinkleContextError, NeckWrinkleScaleError, NeckWrinkleUnavailable,
    available,
)

ALGORITHM_VERSION = 'rapidretouch-neck-full-grid-v1'
MAX_LOG_GAIN = math.log(1.25)
MAX_LIGHTNESS_LIFT = 6.0
MIN_HALF_WIDTH = 1.4
MAX_HALF_WIDTH = 12.0
MAX_PIXELS = 32_000_000
MAX_DIMENSION = 65_536
MAX_WORKING_BYTES = 4 * 1024**3
ALLOWANCE_BYTES = 8 * 1024**2
BLOCK_PIXELS = 4096
ENCODING = 'encoded-working-srgb-d65-sdr'


@dataclass(frozen=True)
class PreparedNeckField:
    """Transient immutable measured proposal, never self-authenticating provenance.

    log_gain and eligible_mask are bytes-backed, contiguous and truly read-only.
    eligible_mask is complete-context support independent of detected signal.
    facts returns a fresh JSON object, preventing mutation of stored facts while
    remaining JSON-safe for host diagnostics. changed_pixels counts positive
    source-measured proposals, NOT visible/current-stage changed pixels.
    """
    window_yxhw: tuple
    log_gain: np.ndarray
    eligible_mask: np.ndarray
    source_shape_hw: tuple
    algorithm_version: str
    _facts_json: str

    @property
    def facts(self):
        return json.loads(self._facts_json)


def _shape(value):
    if type(value) not in (tuple, list) or len(value) != 2:
        raise ValueError('Neck source dimensions require exact (height,width)')
    h, w = value
    if any(type(v) is not int or v < 1 or v > MAX_DIMENSION for v in (h, w)):
        raise ValueError('Neck source dimensions are outside the supported range')
    if h*w > MAX_PIXELS:
        raise MemoryError('Neck source exceeds its 32 MP bound; no reduced-grid fallback')
    return h, w


def _number(value, low, high, label):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(label + ' requires a finite number, not a boolean')
    try:
        v = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(label + ' requires a finite number') from error
    if not math.isfinite(v) or not low <= v <= high:
        raise ValueError(label + ' is outside its supported range')
    return v


def _policy(value):
    try:
        s = _number(value, MIN_HALF_WIDTH, MAX_HALF_WIDTH, 'Neck line half-width')
    except ValueError as error:
        raise NeckWrinkleScaleError('Observed fine-line half-width must be 1.4..12 canonical pixels') from error
    sigmas = (0.5*s, 0.75*s, s)
    close = math.ceil(2.5*s)
    filled = math.ceil(3*max(0.5, 0.5*s))
    pore = math.ceil(3*max(0.5, 0.3*s))
    spread = math.ceil(1.5*s)
    fold = math.ceil(3*s)
    gaussian = math.ceil(3*s)
    depth = 2*close + filled + pore
    weight = gaussian + 2 + spread + gaussian
    radius = max(weight, depth + fold + gaussian)
    return s, sigmas, radius


def _window(value, shape):
    if type(value) not in (tuple, list) or len(value) != 4 or any(type(v) is not int for v in value):
        raise ValueError('Neck candidate requires exact integer (y,x,height,width)')
    y, x, h, w = value
    if y < 0 or x < 0 or h < 1 or w < 1 or y+h > shape[0] or x+w > shape[1]:
        raise ValueError('Neck candidate window extends outside the canonical source')
    return y, x, h, w


def plan(source_shape_hw, line_half_width_px, candidate_window_yxhw):
    """Allocation-free conservative TOTAL accounted measurement admission.

    required_work_bytes includes resident caller RGB/weight/protection (17N),
    private full-source snapshots (17N), native halo scratch (80S), field buffers
    and immutable retention (15O), plus 8 MiB. Other host residents, support
    rasterization, analysis, repairs and concurrent people must be added by the
    owner, without double-counting this resident 17N. No source/native inspection.
    """
    h, w = _shape(source_shape_hw)
    _, _, radius = _policy(line_half_width_px)
    y, x, oh, ow = _window(candidate_window_yxhw, (h, w))
    sh = min(h, y+oh+radius) - max(0, y-radius)
    sw = min(w, x+ow+radius) - max(0, x-radius)
    needed = 34*h*w + 80*sh*sw + 15*oh*ow + ALLOWANCE_BYTES
    if needed > MAX_WORKING_BYTES:
        raise MemoryError('Neck measurement exceeds its absolute byte bound; no proxy fallback')
    return {'window_yxhw': (y, x, oh, ow), 'dependency_radius_px': radius,
            'required_work_bytes': needed, 'retained_bytes': 5*oh*ow,
            'algorithm_version': ALGORITHM_VERSION}


def _cancelled(value):
    if value is None:
        return lambda: False
    if not callable(value):
        raise TypeError('cancelled must be a callable or None')
    return value


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Neck wrinkle cancelled; private output discarded')


def _array(value, dtype, shape, label):
    if type(value) is not np.ndarray or value.dtype != dtype or value.shape != shape:
        raise ValueError(label + ' requires exact native dtype and shape ' + str(shape))


def _blocks(shape):
    for row in range(shape[0]):
        for left in range(0, shape[1], BLOCK_PIXELS):
            yield row, slice(left, min(left+BLOCK_PIXELS, shape[1]))


def _snapshot(value, cancelled, label, *, bound=1.0):
    _poll(cancelled)
    out = np.empty(value.shape, dtype=value.dtype, order='C')
    for row, columns in _blocks(value.shape):
        _poll(cancelled)
        block = out[row, columns]
        block[...] = value[row, columns]
        if value.dtype != np.bool_ and (not np.isfinite(block).all() or np.any(block < 0) or np.any(block > bound)):
            raise ValueError(label + ' requires finite bounded SDR values; no clipping or flattening')
    out.setflags(write=False)
    _poll(cancelled)
    return out


def _candidate(weight, protect, cancelled):
    top, left, bottom, right = weight.shape[0], weight.shape[1], -1, -1
    for row, columns in _blocks(weight.shape):
        _poll(cancelled)
        block = weight[row, columns]
        if not np.isfinite(block).all() or np.any(block < 0) or np.any(block > 1):
            raise ValueError('Neck admitted weight requires finite [0,1]')
        indices = np.flatnonzero((block > 0) & ~protect[row, columns])
        if indices.size:
            top = min(top, row)
            bottom = row
            left = min(left, columns.start + int(indices[0]))
            right = max(right, columns.start + int(indices[-1]))
    if bottom < top:
        raise NeckWrinkleContextError('No admitted unprotected neck skin; not a zero-signal measurement')
    return top, left, bottom-top+1, right-left+1


def measure(source_rgb_f32, admitted_weight_f32, hard_protect_bool, *,
            line_half_width_px, byte_budget, cancelled=None):
    """Measure actual full-source ENCODED working-sRGB; no source authority here.

    Callers must keep all inputs stable while snapshots are made, and serialize
    edits through the canonical source owner. Alpha/HDR, proxies, wrong support,
    stale identity and repair evidence are refused by their respective owners.
    Every output's full dependency square must be positive-weight, unprotected
    genuine source skin. Positive fractional weight attenuates the final lift;
    a protection is an independent veto, never an editable opacity.
    """
    cancelled = _cancelled(cancelled)
    _poll(cancelled)
    if type(source_rgb_f32) is not np.ndarray or source_rgb_f32.ndim != 3 or source_rgb_f32.shape[-1] != 3:
        raise ValueError('Neck measurement requires opaque HWC RGB, not alpha or a proxy packet')
    h, w = _shape(source_rgb_f32.shape[:2])
    _array(source_rgb_f32, np.float32, (h, w, 3), 'Canonical source RGB')
    _array(admitted_weight_f32, np.float32, (h, w), 'Admitted neck weight')
    _array(hard_protect_bool, np.bool_, (h, w), 'Independent hard neck protection')
    scale, sigmas, radius = _policy(line_half_width_px)
    if type(byte_budget) is not int or not 0 <= byte_budget <= MAX_WORKING_BYTES:
        raise ValueError('byte_budget must be an integer 0..4 GiB total operation allowance')
    # Bounded 4096-pixel scans only, before any image-sized allocation.
    window = _candidate(admitted_weight_f32, hard_protect_bool, cancelled)
    layout = plan((h, w), scale, window)
    if layout['required_work_bytes'] > byte_budget:
        raise MemoryError('Neck measurement exceeds its supplied aggregate admission')
    extra = layout['required_work_bytes'] - 17*h*w
    if extra > _available_estimate():
        raise MemoryError('Insufficient verified CPU memory for neck source-grid measurement')
    lib = _native.native()
    _poll(cancelled)
    source = _snapshot(source_rgb_f32, cancelled, 'Canonical source RGB')
    weight = _snapshot(admitted_weight_f32, cancelled, 'Admitted neck weight')
    protect = _snapshot(hard_protect_bool, cancelled, 'Independent protection')
    # Snapshot changes must not turn a previous small plan into a truncated solve.
    if _candidate(weight, protect, cancelled) != window:
        raise ValueError('Neck support changed during capture; measurement discarded')
    y, x, oh, ow = window
    field = np.empty((oh, ow), dtype=np.float32)
    eligible = np.empty((oh, ow), dtype=np.uint8)
    counts = np.zeros(4, dtype=np.uint64)
    metrics = np.zeros(2, dtype=np.float64)
    cb, errors = _native.callback(cancelled)
    code = lib.lrt_neck_wrinkle_measure_v1(
        source.ctypes.data_as(_native.P), source.size,
        weight.ctypes.data_as(_native.P), weight.size,
        protect.ctypes.data_as(_native.BP), protect.size, w, h, y, x, oh, ow,
        scale, byte_budget, field.ctypes.data_as(_native.P), field.size,
        eligible.ctypes.data_as(_native.BP), eligible.size,
        counts.ctypes.data_as(_native.UP), counts.size,
        metrics.ctypes.data_as(_native.DP), metrics.size, cb, None)
    _native.result(code, errors)
    _poll(cancelled)
    changed = eligible_count = 0
    for row, columns in _blocks(field.shape):
        _poll(cancelled)
        block = field[row, columns]
        permission = weight[y+row, x+columns.start:x+columns.stop]
        veto = protect[y+row, x+columns.start:x+columns.stop]
        eligibility = eligible[row, columns]
        if (not np.isfinite(block).all() or np.any(block < 0) or np.any(block > MAX_LOG_GAIN+1e-8)
                or np.any(block[(permission <= 0) | veto] != 0)
                or np.any(eligibility > 1) or np.any(eligibility[(permission <= 0) | veto] != 0)
                or np.any(block[eligibility == 0] != 0)):
            raise RuntimeError('Neck core returned invalid/protected evidence; discarded')
        changed += int(np.count_nonzero(block))
        eligible_count += int(np.count_nonzero(eligibility))
    supported, rejected, lines, native_changed = (int(v) for v in counts)
    if (not 0 < supported <= oh*ow or supported != eligible_count or rejected+supported > oh*ow
            or not 0 <= native_changed <= lines <= supported or native_changed != changed
            or not np.isfinite(metrics).all() or not 0 <= metrics[0] <= MAX_LIGHTNESS_LIFT
            or not 0 <= metrics[1] <= MAX_LOG_GAIN+1e-8):
        raise RuntimeError('Neck core returned inconsistent diagnostics; discarded')
    reason = None
    if changed == 0:
        reason = 'no_detected_wrinkle_lines' if lines == 0 else 'no_positive_wrinkle_lift'
    facts = {'supported_pixels': supported, 'context_rejected_pixels': rejected,
             'line_pixels': lines, 'changed_pixels': changed,
             'changed_pixels_kind': 'positive_source_measured_proposals_not_rendered_pixels',
             'maximum_proposed_lightness_lift': float(metrics[0]),
             'maximum_log_gain': float(metrics[1]), 'sigma_px': list(sigmas),
             'dependency_radius_px': radius, 'no_signal_reason': reason,
             'status': reason or 'measured_proposal', 'runtime_quality_accepted': False,
             'algorithm_version': ALGORITHM_VERSION, 'native_abi': ABI,
             'required_work_bytes': layout['required_work_bytes'],
             'retained_bytes': layout['retained_bytes'],
             'source_grid_shape_hw': [h, w], 'chroma_borrowing': False,
             'full_source_grid': True, 'source_encoding': ENCODING}
    # bytes-backed arrays cannot be made writable with setflags(write=True).
    immutable = np.frombuffer(field.tobytes(order='C'), dtype=np.float32).reshape((oh, ow))
    immutable_eligible = np.frombuffer(eligible.tobytes(order='C'), dtype=np.bool_).reshape((oh, ow))
    _poll(cancelled)
    return PreparedNeckField(window, immutable, immutable_eligible, (h, w), ALGORITHM_VERSION,
                             json.dumps(facts, allow_nan=False, sort_keys=True))


def apply(current_rgb_f32, log_gain_f32, *, amount):
    """Apply a same-grid scalar field to CURRENT LINEAR RGB with common headroom.

    Tile slicing/origin/source ownership belongs to the composition adapter. No
    sRGB conversion here. Field/current zero and zero headroom remain exact input
    bytes. This never clips individual channels or uses source RGB as a patch.
    """
    amount = _number(amount, 0.0, 1.0, 'Neck amount')
    if amount == 0.0:
        return current_rgb_f32
    if type(current_rgb_f32) is not np.ndarray or current_rgb_f32.ndim != 3 or current_rgb_f32.shape[-1] != 3:
        raise ValueError('Neck application requires opaque current linear RGB HWC')
    h, w = _shape(current_rgb_f32.shape[:2])
    _array(current_rgb_f32, np.float32, (h, w, 3), 'Current linear RGB')
    _array(log_gain_f32, np.float32, (h, w), 'Source-measured log-gain field')
    active = False
    for row, columns in _blocks((h, w)):
        rgb = current_rgb_f32[row, columns]
        field = log_gain_f32[row, columns]
        if (not np.isfinite(rgb).all() or np.any(rgb < 0) or np.any(rgb > 1)
                or not np.isfinite(field).all() or np.any(field < 0) or np.any(field > MAX_LOG_GAIN+1e-8)):
            raise ValueError('Neck apply requires finite SDR current RGB and bounded nonnegative field')
        peak = np.max(rgb, axis=-1)
        active = active or bool(np.any((field > 0) & (peak > 0) & (peak < 1)))
    if not active:
        return current_rgb_f32
    required = 56*h*w + ALLOWANCE_BYTES
    if required > MAX_WORKING_BYTES or required-16*h*w > _available_estimate():
        raise MemoryError('Neck current-stage composition exceeds its verified CPU budget')
    lib = _native.native()
    no_cancel = lambda: False
    current = _snapshot(current_rgb_f32, no_cancel, 'Current linear RGB')
    field = _snapshot(log_gain_f32, no_cancel, 'Source log gain', bound=MAX_LOG_GAIN+1e-8)
    output = np.empty_like(current)
    cb, errors = _native.callback(no_cancel)
    code = lib.lrt_neck_wrinkle_apply_v1(current.ctypes.data_as(_native.P), current.size,
        field.ctypes.data_as(_native.P), field.size, w, h, amount,
        output.ctypes.data_as(_native.P), output.size, cb, None)
    _native.result(code, errors)
    changed = False
    for row, columns in _blocks((h, w)):
        block = output[row, columns]
        original = current[row, columns]
        peak = np.max(original, axis=-1)
        untouched = (field[row, columns] == 0) | (peak == 0) | (peak == 1)
        if not np.isfinite(block).all() or np.any(block < 0) or np.any(block > 1):
            raise RuntimeError('Neck core returned non-SDR current-stage output')
        if not np.array_equal(block[untouched].view(np.uint32), original[untouched].view(np.uint32)):
            raise RuntimeError('Neck core changed exact-neutral or zero-headroom pixels')
        changed = changed or not np.array_equal(block.view(np.uint32), original.view(np.uint32))
    return output if changed else current_rgb_f32
