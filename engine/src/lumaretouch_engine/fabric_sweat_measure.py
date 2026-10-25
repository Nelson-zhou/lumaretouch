# SPDX-License-Identifier: GPL-3.0-or-later
"""Full-source Rust measurement and application; authored / UNRUN."""
from dataclasses import dataclass
import ctypes as C
import json
import numpy as np
from . import fabric_sweat_native as N
from . import fabric_sweat_state as S


def _rgb(value):
    if (type(value) is not np.ndarray or value.dtype != np.float32 or value.ndim != 3
            or value.shape[2] != 3 or min(value.shape[:2]) < 1 or max(value.shape[:2]) > 65536
            or value.shape[0] * value.shape[1] > 32_000_000):
        raise ValueError('Fabric sweat requires full-grid float32 RGB')
    for first in range(0, value.shape[0], 32):
        stripe = value[first:first + 32]
        if not np.isfinite(stripe).all() or np.any((stripe < 0) | (stripe > 1)):
            raise ValueError('Fabric sweat refuses nonfinite or non-SDR RGB')
    return value


def _budget(value, required):
    if type(value) is not int or value < required or required > 4 * 1024**3:
        raise MemoryError('Fabric sweat full-source memory admission refused')
    return min(value, 4 * 1024**3)


def _linear(encoded):
    result = np.empty_like(encoded)
    for first in range(0, encoded.shape[0], 32):
        row = encoded[first:first + 32]
        result[first:first + 32] = np.where(row <= .04045, row / 12.92, ((row + .055) / 1.055) ** 2.4)
    return result


def _encoded(linear):
    result = np.empty_like(linear)
    for first in range(0, linear.shape[0], 32):
        row = linear[first:first + 32]
        result[first:first + 32] = np.where(row <= .0031308, row * 12.92, 1.055 * row ** (1 / 2.4) - .055)
    return result


@dataclass(frozen=True)
class Prepared:
    height: int
    width: int
    _field: bytes
    _eligible: bytes
    _target: bytes
    _protect: bytes
    _facts: str

    @property
    def field(self):
        return np.frombuffer(self._field, dtype=np.float32).reshape(self.height, self.width, 3)

    @property
    def eligible(self):
        return np.frombuffer(self._eligible, dtype=np.uint8).reshape(self.height, self.width)

    @property
    def target(self):
        return np.frombuffer(self._target, dtype=np.float32).reshape(self.height, self.width)

    @property
    def protect(self):
        return np.frombuffer(self._protect, dtype=np.uint8).reshape(self.height, self.width)

    @property
    def facts(self):
        return json.loads(self._facts)


def prepare(encoded_rgb, recipe, *, byte_budget, cancelled=None):
    recipe = S.check(recipe)
    if recipe is None or recipe['amount'] == 0:
        return None
    rgb = _rgb(encoded_rgb); h, w = rgb.shape[:2]; pixels = h * w
    if recipe['source']['width'] != w or recipe['source']['height'] != h:
        raise ValueError('Fabric sweat source must not be resized for measurement')
    # Caller source, masks/raster scratch, linear conversion, native/snapshots,
    # immutable retained output are all charged conservatively before allocation.
    required = 196 * pixels + 160 * 1024**2
    byte_budget = _budget(byte_budget, required)
    from .fabric_sweat_support import rasterize
    masks = rasterize(recipe['review'], recipe['source'], byte_budget=byte_budget - 24 * pixels, cancelled=cancelled)
    linear = np.ascontiguousarray(_linear(rgb))
    garment, target, reference = (np.ascontiguousarray(masks[k], dtype=np.float32) for k in ('garment', 'target', 'reference'))
    protect = np.ascontiguousarray(masks['protect'], dtype=np.uint8)
    field = np.zeros((h, w, 3), dtype=np.float32); eligible = np.zeros((h, w), dtype=np.uint8)
    counts = np.zeros(4, np.uint64); metrics = np.zeros(4, np.float64)
    cb, errors = N.callback(cancelled)
    native_budget = byte_budget - 68 * pixels - 128 * 1024**2
    code = N.native().lrt_fabric_sweat_measure_v1(
        linear.ctypes.data_as(N.P), linear.size,
        garment.ctypes.data_as(N.P), garment.size,
        target.ctypes.data_as(N.P), target.size,
        reference.ctypes.data_as(N.P), reference.size,
        protect.ctypes.data_as(N.B), protect.size,
        w, h, recipe['radius_px'], native_budget,
        field.ctypes.data_as(N.P), field.size, eligible.ctypes.data_as(N.B), eligible.size,
        counts.ctypes.data_as(N.U), counts.size, metrics.ctypes.data_as(N.D), metrics.size, cb, None)
    N.checked(code, errors)
    if not np.isfinite(field).all() or np.any(eligible > 1) or np.any((eligible > 0) & ((target <= 0) | (protect > 0))):
        raise RuntimeError('Fabric sweat native output violated source support')
    facts = {'algorithm': 'reference-log-field-v1', 'source_size': [w, h],
        'target_pixels': int(counts[0]), 'eligible_pixels': int(counts[1]),
        'context_rejected_pixels': int(counts[2]), 'proposal_pixels': int(counts[3]),
        'reference_mass': float(metrics[0]), 'reference_log_spread': float(metrics[1]),
        'max_absolute_log_gain': float(metrics[2]), 'minimum_local_support': float(metrics[3]),
        'manual_reference': True, 'runtime_quality_accepted': False}
    return Prepared(h, w, field.tobytes(), eligible.tobytes(), target.tobytes(), protect.tobytes(),
                    json.dumps(facts, allow_nan=False, separators=(',', ':')))


def apply_linear(current_rgb, field, *, amount, byte_budget, cancelled=None):
    amount = S.amount(amount)
    if amount == 0 or field is None:
        return current_rgb
    current = _rgb(current_rgb); h, w = current.shape[:2]
    if type(field) is not np.ndarray or field.dtype != np.float32 or field.shape != current.shape:
        raise ValueError('Fabric sweat measured field must match the current source-grid tile')
    byte_budget = _budget(byte_budget, 80 * h * w + 1024**2)
    # Private stable snapshots; no foreign caller mutation while ctypes releases GIL.
    cur = np.array(current, dtype=np.float32, order='C', copy=True)
    gain = np.array(field, dtype=np.float32, order='C', copy=True)
    output = np.empty_like(cur); cb, errors = N.callback(cancelled)
    code = N.native().lrt_fabric_sweat_apply_v1(cur.ctypes.data_as(N.P), cur.size,
        gain.ctypes.data_as(N.P), gain.size, w, h, amount, byte_budget,
        output.ctypes.data_as(N.P), output.size, cb, None)
    N.checked(code, errors)
    return output


def apply(current_encoded_rgb, prepared, *, amount, byte_budget, origin_yx=(0, 0), cancelled=None):
    amount = S.amount(amount)
    if amount == 0 or prepared is None:
        return current_encoded_rgb
    current = _rgb(current_encoded_rgb); h, w = current.shape[:2]
    if not isinstance(prepared, Prepared) or type(origin_yx) not in (tuple, list) or len(origin_yx) != 2 or any(type(v) is not int or v < 0 for v in origin_yx):
        raise ValueError('Fabric sweat requires its prepared field and exact tile origin')
    y, x = origin_yx
    if y + h > prepared.height or x + w > prepared.width:
        raise ValueError('Fabric sweat tile lies outside the canonical measured source')
    field = prepared.field[y:y + h, x:x + w]
    return apply_field(current, field, amount=amount, byte_budget=byte_budget, cancelled=cancelled)


def apply_field(current_encoded_rgb, field, *, amount, byte_budget, cancelled=None):
    """Apply a caller-sliced measured field; caller proves source/tile provenance."""
    amount = S.amount(amount)
    if amount == 0 or field is None:
        return current_encoded_rgb
    current = _rgb(current_encoded_rgb); h, w = current.shape[:2]
    byte_budget = _budget(byte_budget, 116 * h * w + 4 * 1024**2)
    linear = _linear(current)
    changed = apply_linear(linear, field, amount=amount, byte_budget=byte_budget - 36 * h * w - 3 * 1024**2, cancelled=cancelled)
    out = _encoded(changed)
    # Preserve exact source bits wherever native made no channel change, avoiding
    # gamma round-trip drift outside masks and at exact no-op/headroom pixels.
    for first in range(0, h, 32):
        unchanged = np.all(changed[first:first + 32] == linear[first:first + 32], axis=2)
        out[first:first + 32][unchanged] = current[first:first + 32][unchanged]
    return out
