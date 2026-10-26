# SPDX-License-Identifier: GPL-3.0-or-later
"""Full-source Rust measurement and application; authored / UNRUN."""
from dataclasses import dataclass
import ctypes as C
import json
import math
import numpy as np
from . import hand_tone_native as N
from . import hand_tone_state as S


def _rgb(value):
    if (type(value) is not np.ndarray or value.dtype != np.float32 or value.ndim != 3
            or value.shape[2] != 3 or min(value.shape[:2]) < 1 or max(value.shape[:2]) > 65536
            or value.shape[0] * value.shape[1] > 32_000_000):
        raise ValueError('Hand tone requires full-grid float32 RGB')
    for first in range(0, value.shape[0], 32):
        stripe = value[first:first + 32]
        if not np.isfinite(stripe).all() or np.any((stripe < 0) | (stripe > 1)):
            raise ValueError('Hand tone refuses nonfinite or non-SDR RGB')
    return value


def _budget(value, required):
    if type(value) is not int or value < required or required > 4 * 1024**3:
        raise MemoryError('Hand tone full-source memory admission refused')
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


# Peak accounting deliberately includes full-grid source/masks/frozen outputs.
# Native box moments scale with ROI pixels, never with display/proxy dimensions.
FULL_RESERVE_PER_PIXEL = 80
ROI_RESERVE_PER_PIXEL = 228
FIXED_RESERVE = 160 * 1024**2


def _needed(full_pixels, roi_pixels):
    return FULL_RESERVE_PER_PIXEL * full_pixels + ROI_RESERVE_PER_PIXEL * roi_pixels + FIXED_RESERVE


def planned_roi(recipe):
    """Conservative brush envelope for upstream export admission; no raster/runtime.

    An ellipse swept along a segment stays inside endpoint extrema plus its
    axis support. Only add objects can expand support; subtract and hand/protect
    intersections can only shrink it. Include actual source feather and kernel halo.
    """
    recipe = S.check(recipe)
    if not S.active(recipe): return None
    w, h = recipe['source']['width'], recipe['source']['height']
    x0, y0, x1, y1 = w, h, 0, 0
    for obj in recipe['review']['target']['objects']:
        if not obj['enabled'] or obj['operation'] != 'add' or obj['opacity'] <= 0: continue
        axes = obj['axes']
        ex = math.hypot(axes[0][0], axes[1][0]) * w
        ey = math.hypot(axes[0][1], axes[1][1]) * h
        halo = math.ceil(obj['feather'] * .0005 * min(h, w)) + recipe['radius_px'] + 2
        xs = [point[0] * w - .5 for point in obj['points']]
        ys = [point[1] * h - .5 for point in obj['points']]
        x0 = min(x0, max(0, math.floor(min(xs) - ex) - halo))
        y0 = min(y0, max(0, math.floor(min(ys) - ey) - halo))
        x1 = max(x1, min(w, math.ceil(max(xs) + ex) + halo + 1))
        y1 = max(y1, min(h, math.ceil(max(ys) + ey) + halo + 1))
    if x1 <= x0 or y1 <= y0: raise ValueError('Hand tone has no planned target support')
    return y0, x0, y1, x1


def preparation_bytes(recipe):
    """Conservative source-grid estimate, including a brush-derived ROI envelope."""
    recipe = S.check(recipe)
    roi = planned_roi(recipe)
    if roi is None: return 0
    y0, x0, y1, x1 = roi
    return _needed(recipe['source']['width'] * recipe['source']['height'], (y1-y0)*(x1-x0))


def _target_roi(target, radius, cancelled=None):
    """Find real admitted target support in bounded stripes, plus complete halo."""
    h, w = target.shape
    y0, x0, y1, x1 = h, w, 0, 0
    for first in range(0, h, 32):
        if cancelled and cancelled(): raise InterruptedError('Hand tone ROI scan cancelled')
        painted = target[first:first+32] > 0
        rows = np.flatnonzero(np.any(painted, axis=1))
        if not rows.size: continue
        cols = np.flatnonzero(np.any(painted, axis=0))
        y0, y1 = min(y0, first+int(rows[0])), max(y1, first+int(rows[-1])+1)
        x0, x1 = min(x0, int(cols[0])), max(x1, int(cols[-1])+1)
    if x1 <= x0 or y1 <= y0: raise ValueError('No unprotected hand target remains')
    return max(0,y0-radius), max(0,x0-radius), min(h,y1+radius), min(w,x1+radius)


def prepare(encoded_rgb, recipe, *, byte_budget, cancelled=None):
    recipe = S.check(recipe)
    if recipe is None or recipe['amount'] == 0:
        return None
    rgb = _rgb(encoded_rgb); h, w = rgb.shape[:2]; pixels = h * w
    if recipe['source']['width'] != w or recipe['source']['height'] != h:
        raise ValueError('Hand tone source must not be resized for measurement')
    # First admit full-grid capture/mask/retained-output work, before rasterizing.
    # 12N source + 9N masks + 13N full outputs + 18N immutable copies = 52N;
    # reserve 80N for simultaneous owner views, stripe checks and mask temporaries.
    # An additional 228R covers native160R and Python ROI conversions/outputs68R.
    byte_budget = _budget(byte_budget, _needed(pixels, 0))
    from .hand_tone_support import rasterize
    masks = rasterize(recipe['review'], recipe['source'], byte_budget=byte_budget - 24 * pixels, cancelled=cancelled)
    target, protect = masks['target'], masks['protect']
    y0, x0, y1, x1 = _target_roi(target, recipe['radius_px'], cancelled)
    rh, rw = y1-y0, x1-x0; roi_pixels = rh*rw
    byte_budget = _budget(byte_budget, _needed(pixels, roi_pixels))
    # No resizing/reprojection: one contiguous exact crop of canonical pixels.
    # Every target dependency box lies within this halo, except a genuine source
    # edge where native deliberately rejects; ROI borders cannot add context.
    linear = np.ascontiguousarray(_linear(rgb[y0:y1,x0:x1]))
    limb_roi = np.ascontiguousarray(masks['limb'][y0:y1,x0:x1], dtype=np.float32)
    target_roi = np.ascontiguousarray(target[y0:y1,x0:x1], dtype=np.float32)
    protect_roi = np.ascontiguousarray(protect[y0:y1,x0:x1], dtype=np.uint8)
    roi_field = np.zeros((rh,rw,3), dtype=np.float32)
    roi_eligible = np.zeros((rh,rw), dtype=np.uint8)
    counts = np.zeros(4, np.uint64); metrics = np.zeros(4, np.float64)
    cb, errors = N.callback(cancelled)
    native_budget = byte_budget - FULL_RESERVE_PER_PIXEL * pixels - 68 * roi_pixels - 128 * 1024**2
    code = N.native().lrt_hand_tone_measure_v1(
        linear.ctypes.data_as(N.P), linear.size,
        limb_roi.ctypes.data_as(N.P), limb_roi.size,
        target_roi.ctypes.data_as(N.P), target_roi.size,
        protect_roi.ctypes.data_as(N.B), protect_roi.size,
        rw, rh, recipe['radius_px'], native_budget,
        roi_field.ctypes.data_as(N.P), roi_field.size, roi_eligible.ctypes.data_as(N.B), roi_eligible.size,
        counts.ctypes.data_as(N.U), counts.size, metrics.ctypes.data_as(N.D), metrics.size, cb, None)
    N.checked(code, errors)
    if not np.isfinite(roi_field).all() or np.any(roi_eligible > 1) or np.any((roi_eligible > 0) & ((target_roi <= 0) | (protect_roi > 0))):
        raise RuntimeError('Hand tone native output violated source support')
    field = np.zeros((h,w,3), dtype=np.float32)
    eligible = np.zeros((h,w), dtype=np.uint8)
    field[y0:y1,x0:x1] = roi_field
    eligible[y0:y1,x0:x1] = roi_eligible
    del linear, limb_roi, target_roi, protect_roi, roi_field, roi_eligible
    facts = {'algorithm': 'hand-tone-local-log-luminance-band-v1', 'source_size': [w, h],
        'target_pixels': int(counts[0]), 'eligible_pixels': int(counts[1]),
        'context_rejected_pixels': int(counts[2]), 'proposal_pixels': int(counts[3]),
        'max_absolute_log_gain': float(metrics[2]), 'minimum_local_support': float(metrics[3]),
        'maximum_band_contrast': float(metrics[0]), 'maximum_coarse_log_luminance_sigma': float(metrics[1]),
        'manual_hand_support': True, 'limb_kind': 'hand',
        'measurement_roi_xywh': [x0,y0,rw,rh], 'roi_source_scale': 1,
        'measurement_admission_bytes': _needed(pixels,roi_pixels),
        'automatic_anatomy': False, 'luminance_only': True, 'runtime_quality_accepted': False}
    return Prepared(h, w, field.tobytes(), eligible.tobytes(), target.tobytes(), protect.tobytes(),
                    json.dumps(facts, allow_nan=False, separators=(',', ':')))


def apply_linear(current_rgb, field, *, amount, byte_budget, cancelled=None):
    amount = S.amount(amount)
    if amount == 0 or field is None:
        return current_rgb
    current = _rgb(current_rgb); h, w = current.shape[:2]
    if type(field) is not np.ndarray or field.dtype != np.float32 or field.shape != current.shape:
        raise ValueError('Hand tone measured field must match the current source-grid tile')
    byte_budget = _budget(byte_budget, 80 * h * w + 1024**2)
    # Private stable snapshots; no foreign caller mutation while ctypes releases GIL.
    cur = np.array(current, dtype=np.float32, order='C', copy=True)
    gain = np.array(field, dtype=np.float32, order='C', copy=True)
    output = np.empty_like(cur); cb, errors = N.callback(cancelled)
    code = N.native().lrt_hand_tone_apply_v1(cur.ctypes.data_as(N.P), cur.size,
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
        raise ValueError('Hand tone requires its prepared field and exact tile origin')
    y, x = origin_yx
    if y + h > prepared.height or x + w > prepared.width:
        raise ValueError('Hand tone tile lies outside the canonical measured source')
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
