# SPDX-License-Identifier: GPL-3.0-or-later
"""V2 bounded stroke-local staging; same source-centre capsule math, UNRUN.

Unlike v1, zero coverage outside each stroke's enclosing rectangle is not scanned
or stored. No vector thinning, raster downsampling or feather simplification.
"""
from .lens_blur_refinement import (_shape, _segments, _bounds, validate_strokes,
                                   BLOCK_PIXELS, SCRATCH_BYTES)


def _stroke_plan(stroke, width, height):
    radius = stroke['radius'] * min(width, height)
    segments = [(a, b, _bounds(a, b, radius, width, height))
                for a, b in _segments(stroke, width, height)]
    live = [rect for _, _, rect in segments if rect[0] <= rect[2] and rect[1] <= rect[3]]
    if not live:
        return radius, segments, None
    box = (min(r[0] for r in live), min(r[1] for r in live),
           max(r[2] for r in live), max(r[3] for r in live))
    return radius, segments, box


def estimate(strokes, width, height):
    _shape(width, height); validate_strokes(strokes)
    active = [s for s in strokes if s['amount'] * s['flow'] > 0]
    if not active:
        return {'pixels_examined': 0, 'peak_bytes': 0}
    examined = width * height * 2  # Output zero-fill and immutable conversion.
    for stroke in active:
        _, segments, box = _stroke_plan(stroke, width, height)
        for _, _, (left, top, right, bottom) in segments:
            examined += max(0, right-left+1) * max(0, bottom-top+1)
        if box is not None:
            left, top, right, bottom = box
            examined += 2 * (right-left+1) * (bottom-top+1)  # Coverage fill and blend.
    # Either output+one bounded coverage or output+immutable bytes, never all3.
    return {'pixels_examined': examined, 'peak_bytes': width * height * 8 + SCRATCH_BYTES}


def rasterize(strokes, width, height, *, max_bytes, max_pixels_examined, cancelled=lambda: False):
    work = estimate(strokes, width, height)
    if type(max_bytes) is not int or max_bytes < work['peak_bytes']:
        raise MemoryError('V2 stroke-local refinement exceeds its reserved byte budget')
    if type(max_pixels_examined) is not int or max_pixels_examined < work['pixels_examined']:
        raise MemoryError('V2 source refinement exceeds its actual scan budget; no strokes omitted')
    def poll():
        if cancelled():
            raise InterruptedError('V2 refinement cancelled; private raster discarded')
    poll()
    if work['pixels_examined'] == 0:
        return None
    import numpy as np
    output = np.zeros((height, width), dtype='<f4')
    for stroke in strokes:
        strength = stroke['amount'] * stroke['flow']
        if strength == 0:
            continue
        radius, segments, box = _stroke_plan(stroke, width, height)
        if box is None:
            continue
        left, top, right, bottom = box
        poll()
        coverage = np.zeros((bottom-top+1, right-left+1), dtype='<f4')
        inner = radius * (1-stroke['feather'])
        for a, b, (x0, y0, x1, y1) in segments:
            vx, vy = b[0]-a[0], b[1]-a[1]
            square = vx*vx + vy*vy
            for y in range(y0, y1+1):
                for x in range(x0, x1+1, BLOCK_PIXELS):
                    poll(); end = min(x1+1, x+BLOCK_PIXELS)
                    dx = np.arange(x, end, dtype=np.float64)-a[0]
                    dy = y-a[1]
                    if square:
                        t = np.clip((dx*vx+dy*vy)/square, 0, 1)
                        distance = np.hypot(dx-t*vx, dy-t*vy)
                    else:
                        distance = np.hypot(dx, dy)
                    if inner >= radius:
                        weights = (distance <= radius).astype(np.float32)
                    else:
                        t = np.clip((distance-inner)/(radius-inner), 0, 1)
                        weights = (1-t*t*(3-2*t)).astype(np.float32)
                    block = coverage[y-top, x-left:end-left]
                    np.maximum(block, weights, out=block)
        sign = -1.0 if stroke['mode'] == 'clear' else 1.0
        for y in range(top, bottom+1):
            for x in range(left, right+1, BLOCK_PIXELS):
                poll(); end = min(right+1, x+BLOCK_PIXELS)
                old = output[y, x:end].astype(np.float64)
                alpha = coverage[y-top, x-left:end-left].astype(np.float64)*strength
                output[y, x:end] = old+(sign-old)*alpha
        # The block view also owns coverage; release before the next allocation.
        if 'block' in locals():
            del block
        del coverage
    poll()
    result = output.tobytes(order='C')
    poll()
    return result
