# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-centre clear/blur rasterizer. AUTHORED / UNRUN.

Each stroke is a continuous polyline with round caps. Its maximum capsule
coverage is composited ONCE, so event frequency and repeated points within a
stroke do not change flow. Separate strokes remain ordered. No display proxy,
point decimation, inferred subject, or depth change is involved.
"""
from __future__ import annotations

import math
import re

MAX_STROKES = 64
MAX_POINTS = 8192
MAX_POINTS_PER_STROKE = 2048
MAX_SOURCE_PIXELS = 100_000_000
BLOCK_PIXELS = 4096
SCRATCH_BYTES = 2 * 1024 * 1024


def _unit(value):
    return type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value)


def validate_strokes(value):
    """Validate exact UI-v1 vectors before allocating or copying any arrays."""
    if type(value) is not list or len(value) > MAX_STROKES:
        raise ValueError('Lens refinements exceed the 64-stroke contract')
    ids, count = set(), 0
    for stroke in value:
        if type(stroke) is not dict or set(stroke) != {'id', 'mode', 'amount', 'flow', 'feather', 'radius', 'points'}:
            raise ValueError('Malformed lens refinement stroke')
        identity = stroke['id']
        if (type(identity) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,128}', identity) is None
                or identity in ids or stroke['mode'] not in ('clear', 'blur')):
            raise ValueError('Lens stroke requires a unique token and clear/blur mode')
        ids.add(identity)
        if any(not _unit(stroke[key]) for key in ('amount', 'flow', 'feather')):
            raise ValueError('Lens stroke amount/flow/feather must be finite unit numbers')
        if not _unit(stroke['radius']) or not 0 < stroke['radius'] <= .25:
            raise ValueError('Lens radius must be in (0,.25] of the source short edge')
        points = stroke['points']
        if type(points) is not list or not 1 <= len(points) <= MAX_POINTS_PER_STROKE:
            raise ValueError('Lens stroke must have 1..2048 actual points')
        count += len(points)
        if count > MAX_POINTS:
            raise ValueError('Lens refinements exceed 8192 points; no thinning is performed')
        for point in points:
            if type(point) is not dict or set(point) != {'x', 'y'} or not all(_unit(point[k]) for k in ('x', 'y')):
                raise ValueError('Lens points require normalized source pixel centres')
    return value


def _shape(width, height):
    if (type(width) is not int or type(height) is not int or min(width, height) < 2
            or max(width, height) > 1_000_000 or width * height > MAX_SOURCE_PIXELS):
        raise ValueError('Invalid full-source lens refinement extent')


def _segments(stroke, width, height):
    points = stroke['points']
    previous = (points[0]['x'] * (width - 1), points[0]['y'] * (height - 1))
    if len(points) == 1:
        yield previous, previous
    for point in points[1:]:
        current = (point['x'] * (width - 1), point['y'] * (height - 1))
        yield previous, current
        previous = current


def _bounds(a, b, radius, width, height):
    return (max(0, math.ceil(min(a[0], b[0]) - radius)),
            max(0, math.ceil(min(a[1], b[1]) - radius)),
            min(width - 1, math.floor(max(a[0], b[0]) + radius)),
            min(height - 1, math.floor(max(a[1], b[1]) + radius)))


def estimate(strokes, width, height):
    """Pure worst-case evaluated capsule pixels; no imports or allocations."""
    _shape(width, height)
    validate_strokes(strokes)
    examined = 0
    active = 0
    for stroke in strokes:
        if stroke['amount'] == 0 or stroke['flow'] == 0:
            continue
        active += 1
        radius = stroke['radius'] * min(width, height)
        for a, b in _segments(stroke, width, height):
            left, top, right, bottom = _bounds(a, b, radius, width, height)
            examined += max(0, right - left + 1) * max(0, bottom - top + 1)
    # Count zero-fill/compositing scans and final immutable conversion too.
    if active:
        examined += width * height * (2 + 2 * active)
    # Output, per-stroke coverage, and immutable output conversion coexist.
    return {'pixels_examined': examined, 'peak_bytes': width * height * 12 + SCRATCH_BYTES}


def rasterize(strokes, width, height, *, max_bytes, max_pixels_examined, cancelled=lambda: False):
    """Return immutable little-endian f32 signed refinement, or None if empty.

    Inside each capsule coverage is 1 until radius*(1-feather), then falls by
    1-smoothstep(t), reaching 0 at the outer radius. Feather=0 uses a hard disc.
    Once per stroke: result += (sign-result)*coverage*amount*flow. Clear sign=-1;
    blur sign=+1. Full clear is exactly -1, including after a full blur stroke.
    All distance arithmetic is f64; stored coverage/result is f32. Bounds and
    work are admitted before any full-grid allocation, even for neutral render.
    """
    work = estimate(strokes, width, height)
    if type(max_bytes) is not int or max_bytes < work['peak_bytes']:
        raise MemoryError('Lens refinement exceeds its reserved memory budget')
    if type(max_pixels_examined) is not int or max_pixels_examined < 1 or work['pixels_examined'] > max_pixels_examined:
        raise MemoryError('Lens refinement exceeds its explicit work budget; no vector reduction')
    if not callable(cancelled):
        raise TypeError('Lens cancellation must be callable')
    def poll():
        if cancelled():
            raise InterruptedError('Lens refinement cancelled; private raster discarded')
    poll()
    if not strokes or not any(s['amount'] * s['flow'] > 0 for s in strokes):
        return None
    import numpy as np
    output = np.zeros((height, width), dtype='<f4')
    coverage = np.empty((height, width), dtype='<f4')
    for stroke in strokes:
        poll()
        strength = stroke['amount'] * stroke['flow']
        if strength == 0:
            continue
        coverage.fill(0)
        radius = stroke['radius'] * min(width, height)
        inner = radius * (1 - stroke['feather'])
        for a, b in _segments(stroke, width, height):
            left, top, right, bottom = _bounds(a, b, radius, width, height)
            vx, vy = b[0] - a[0], b[1] - a[1]
            square = vx * vx + vy * vy
            for y in range(top, bottom + 1):
                for x in range(left, right + 1, BLOCK_PIXELS):
                    poll()
                    end = min(right + 1, x + BLOCK_PIXELS)
                    dx = np.arange(x, end, dtype=np.float64) - a[0]
                    dy = y - a[1]
                    if square:
                        t = np.clip((dx * vx + dy * vy) / square, 0, 1)
                        distance = np.hypot(dx - t * vx, dy - t * vy)
                    else:
                        distance = np.hypot(dx, dy)
                    if inner >= radius:
                        weights = (distance <= radius).astype(np.float32)
                    else:
                        t = np.clip((distance - inner) / (radius - inner), 0, 1)
                        weights = (1 - t * t * (3 - 2 * t)).astype(np.float32)
                    np.maximum(coverage[y, x:end], weights, out=coverage[y, x:end])
        sign = -1.0 if stroke['mode'] == 'clear' else 1.0
        # Bounded compositing work includes complete-plane scans in admission.
        for y in range(height):
            for x in range(0, width, BLOCK_PIXELS):
                poll()
                end = min(width, x + BLOCK_PIXELS)
                old = output[y, x:end].astype(np.float64)
                alpha = coverage[y, x:end].astype(np.float64) * strength
                output[y, x:end] = old + (sign - old) * alpha
    poll()
    result = output.tobytes(order='C')
    poll()
    return result
