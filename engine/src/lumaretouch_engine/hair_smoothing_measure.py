# SPDX-License-Identifier: GPL-3.0-or-later
"""Full-grid immutable numerical transport only. AUTHORED / UNRUN.

The host authenticates source, retained ownership, visible strokes and repair
proof. This module never manufactures that authority from caller RGB plus SHA.
No Python numerical approximation, inference, source replacement or proxy fit.
"""
from dataclasses import dataclass
import json
import math
import numpy as np
from . import hair_smoothing_native as N
from .hair_smoothing_native import (ABI, HairSmoothingUnavailable,
    HairSmoothingContextError, HairSmoothingScaleError, available)

ALGORITHM_VERSION = 'lrt-visible-hair-directional-full-source-v1'
MAX_LOG_GAIN = math.log(1.10)
MIN_TEXTURE_SCALE = 1.0
MAX_TEXTURE_SCALE = 8.0
MAX_PIXELS = 32_000_000
MAX_DIMENSION = 65_536
MAX_WORKING_BYTES = 4 * 1024**3
BLOCK_ROWS = 32


@dataclass(frozen=True)
class PreparedHairSmoothingField:
    log_gain: np.ndarray
    eligible_mask: np.ndarray
    source_shape_hw: tuple
    algorithm_version: str
    _facts_json: str

    @property
    def facts(self):
        return json.loads(self._facts_json)

    @property
    def window_yxhw(self):
        return (0, 0, *self.source_shape_hw)


def _shape(value):
    if type(value) not in (tuple, list) or len(value) != 2 or any(
            type(n) is not int or not 1 <= n <= MAX_DIMENSION for n in value):
        raise ValueError('Hair smoothing requires exact bounded (height,width)')
    h, w = value
    if h*w > MAX_PIXELS:
        raise MemoryError('Hair smoothing source exceeds 32 MP; no proxy fit')
    return h, w


def _number(value, low, high, label):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError(label + ' must be finite and within its admitted range')
    return float(value)


def plan(source_shape_hw, texture_scale_px):
    """Exact checked native plan plus independently mirrored arithmetic.

    Total includes 21N resident caller RGB/target/context/protection bytes,
    wrapper stable snapshots, output and immutable-retention copies, finite
    tensor scratch and integer context-integral scratch. Unrelated host source
    analysis, repairs, rasterization and other effects remain additional costs.
    """
    h, w = _shape(source_shape_hw)
    try:
        scale = _number(texture_scale_px, 1, 8, 'Observed hair texture scale')
    except ValueError as error:
        raise HairSmoothingScaleError('Observed hair texture scale must be 1..8 native pixels') from error
    required = 120*h*w + 8*(w+1)*(h+1) + 16*1024**2
    if required > MAX_WORKING_BYTES:
        raise MemoryError('Hair smoothing plan exceeds the absolute working-memory bound')
    retained = 5*h*w
    halo = math.ceil(0.5*scale) + 1 + math.ceil(2*scale) + 1
    output = (N.C.c_uint64 * 3)()
    N.result(N.native().lrt_hair_smoothing_plan_v1(w, h, scale, output, 3))
    if list(output) != [required, retained, halo]:
        raise HairSmoothingUnavailable('Installed native plan disagrees with the frozen algorithm contract')
    return {'required_work_bytes': required, 'retained_bytes': retained,
            'dependency_radius_px': halo, 'algorithm_version': ALGORITHM_VERSION,
            'source_shape_hw': (h, w), 'window_yxhw': (0, 0, h, w)}


def _cancelled(value):
    if value is None:
        return lambda: False
    if not callable(value):
        raise TypeError('cancelled must be callable or None')
    return value


def _poll(cancelled):
    if cancelled():
        raise InterruptedError('Hair smoothing canceled; private output discarded')


def _budget(value, required):
    if type(value) is not int or not required <= value <= 2**64-1:
        raise MemoryError('Hair smoothing lacks its explicit aggregate byte admission')
    from .cpu_memory_budget import available_estimate
    available = available_estimate()
    if type(available) is not int or required > available:
        raise MemoryError('Hair smoothing exceeds currently available CPU memory; no fallback')
    return min(value, available)


def _array(value, dtype, shape, label):
    if (type(value) is not np.ndarray or value.dtype != dtype or value.shape != shape
            or not value.flags.c_contiguous or not value.flags.aligned):
        raise ValueError(label + ' must have exact native dtype, contiguous aligned layout and source shape')


def _disjoint(values):
    for index, one in enumerate(values):
        for two in values[index+1:]:
            if np.shares_memory(one, two):
                raise ValueError('Hair smoothing inputs must be distinct stable owned buffers')


def _snapshot(value, cancelled, label, *, signed=False):
    output = np.empty(value.shape, dtype=value.dtype, order='C')
    for top in range(0, value.shape[0], BLOCK_ROWS):
        _poll(cancelled)
        block = output[top:top+BLOCK_ROWS]
        block[...] = value[top:top+BLOCK_ROWS]
        if value.dtype != np.bool_:
            low, high = (-MAX_LOG_GAIN, MAX_LOG_GAIN) if signed else (0, 1)
            if not np.isfinite(block).all() or np.any(block < low) or np.any(block > high):
                raise ValueError(label + ' contains nonfinite or out-of-contract values; no clipping')
    output.setflags(write=False)
    return output


def measure(source, target, context, hard_protect, *, texture_scale_px, byte_budget, cancelled=None):
    """One canonical source solve, never a preview/export tile measurement."""
    if type(source) is not np.ndarray or source.ndim != 3 or source.shape[2] != 3:
        raise ValueError('Hair measurement requires full-source f32 HWC RGB')
    shape = _shape(tuple(source.shape[:2])); h, w = shape
    _array(source, np.float32, (*shape, 3), 'Immutable hair source')
    if source.flags.writeable:
        raise ValueError('Hair source must be immutable before numerical admission')
    _array(target, np.float32, shape, 'Owned hair target')
    _array(context, np.float32, shape, 'Owned hair context')
    if type(hard_protect) is not np.ndarray or hard_protect.dtype not in (np.dtype('bool'), np.dtype('uint8')):
        raise ValueError('Hair hard protection must be exact bool or uint8')
    _array(hard_protect, hard_protect.dtype, shape, 'Hard protection')
    _disjoint((source, target, context, hard_protect))
    admission = plan(shape, texture_scale_px)
    budget = _budget(byte_budget, admission['required_work_bytes'])
    cancelled = _cancelled(cancelled); _poll(cancelled)
    rgb = _snapshot(source, cancelled, 'Source RGB')
    owned = _snapshot(target, cancelled, 'Hair target')
    admitted = _snapshot(context, cancelled, 'Hair context')
    hard = _snapshot(hard_protect, cancelled, 'Hard protection').view(np.uint8)
    if np.any((owned > 0) & (admitted <= 0) & (hard == 0)):
        raise ValueError('Every unprotected target center must lie inside its owned context')
    output = np.empty(shape, np.float32); eligible = np.empty(shape, np.uint8)
    counts = np.empty(4, np.uint64); metrics = np.empty(2, np.float64)
    callback, errors = N.callback(cancelled)
    N.result(N.native().lrt_hair_smoothing_measure_v1(
        rgb.ctypes.data_as(N.P), rgb.size, owned.ctypes.data_as(N.P), owned.size,
        admitted.ctypes.data_as(N.P), admitted.size, hard.ctypes.data_as(N.BP), hard.size,
        w, h, float(texture_scale_px), budget, output.ctypes.data_as(N.P), output.size,
        eligible.ctypes.data_as(N.BP), eligible.size, counts.ctypes.data_as(N.UP), counts.size,
        metrics.ctypes.data_as(N.DP), metrics.size, callback, None), errors)
    _poll(cancelled)
    if (not np.isfinite(output).all() or np.any(np.abs(output.astype(np.float64)) > MAX_LOG_GAIN)
            or np.any(eligible > 1) or not np.isfinite(metrics).all()):
        raise RuntimeError('Hair native result violates bounded field/eligibility contract')
    changed = output != 0
    if np.any(changed & ((eligible == 0) | (owned <= 0) | (hard != 0))):
        raise RuntimeError('Hair native field changed ineligible, unowned or protected source centers')
    supported, rejected, directional, proposals = map(int, counts)
    if (supported != int(np.count_nonzero(eligible)) or proposals != int(np.count_nonzero(changed))
            or not 0 <= proposals <= directional <= supported <= h*w or not 0 <= rejected <= h*w
            or supported+rejected != int(np.count_nonzero((owned > 0) & (hard == 0)))
            or metrics[0] != float(np.max(np.abs(output))) or not 0 <= metrics[1] <= 1):
        raise RuntimeError('Hair native diagnostics do not describe its actual eligibility/proposal fields')
    reason = None if proposals else ('no_admitted_directional_signal' if not directional else 'directional_proposals_gated_to_zero')
    facts = {'supported_pixels': supported, 'context_rejected_pixels': rejected,
        'directional_pixels': directional, 'changed_pixels': proposals,
        'no_signal_reason': reason, 'maximum_abs_log_gain': float(metrics[0]),
        'maximum_center_coherence': float(metrics[1]), 'texture_scale_px': float(texture_scale_px),
        'dependency_radius_px': admission['dependency_radius_px'],
        'scope': 'visible-owned-hair-source-direction-luminance-only',
        'clipping_dark_highlight_gates': 'engineering-heuristics-not-physical-classification',
        'runtime_quality_accepted': False}
    # Bytes-backed storage cannot be made writable by downstream setflags().
    frozen = np.frombuffer(output.tobytes(order='C'), dtype=np.float32).reshape(shape)
    eligible_frozen = np.frombuffer(eligible.tobytes(order='C'), dtype=np.bool_).reshape(shape)
    _poll(cancelled)
    return PreparedHairSmoothingField(frozen, eligible_frozen, shape, ALGORITHM_VERSION,
        json.dumps(facts, sort_keys=True, separators=(',', ':'), allow_nan=False))


def apply(current_linear_rgb, field, *, amount, byte_budget=None, cancelled=None):
    """Native common scalar gain on CURRENT linear SDR pixels, not source RGB."""
    amount = _number(amount, 0, 1, 'Hair smoothing amount')
    if type(current_linear_rgb) is not np.ndarray or current_linear_rgb.ndim != 3 or current_linear_rgb.shape[2] != 3:
        raise ValueError('Hair composition requires current linear f32 HWC RGB')
    shape = _shape(tuple(current_linear_rgb.shape[:2])); h, w = shape
    _array(current_linear_rgb, np.float32, (*shape, 3), 'Current linear RGB')
    _array(field, np.float32, shape, 'Frozen signed log-gain')
    _disjoint((current_linear_rgb, field))
    cancelled = _cancelled(cancelled); _poll(cancelled)
    required = 80*h*w+8*1024**2
    budget = _budget(required if byte_budget is None else byte_budget, required)
    current = _snapshot(current_linear_rgb, cancelled, 'Current linear RGB')
    gain = _snapshot(field, cancelled, 'Hair log-gain', signed=True)
    output = np.empty(current.shape, np.float32)
    callback, errors = N.callback(cancelled)
    N.result(N.native().lrt_hair_smoothing_compose_v1(
        current.ctypes.data_as(N.P), current.size, gain.ctypes.data_as(N.P), gain.size,
        w, h, amount, budget, output.ctypes.data_as(N.P), output.size, callback, None), errors)
    _poll(cancelled)
    if not np.isfinite(output).all() or np.any((output < 0) | (output > 1)):
        raise RuntimeError('Hair composition returned nonfinite or out-of-SDR pixels')
    same = gain == 0 if amount else np.ones(shape, dtype=bool)
    if np.any(output.view(np.uint32)[same] != current.view(np.uint32)[same]):
        raise RuntimeError('Hair zero field/amount failed exact identity')
    return output
