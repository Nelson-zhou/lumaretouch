# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase/ROI admission for existing full-source repair replay; not a solver.

AUTHORED / UNRUN. Static conservative allocation envelope, not measured RSS,
throughput, or a guarantee that any arbitrary 24MP repair stack will fit.
"""
import math

FIXED_BYTES = 128 * 1024**2
FULL_BYTES_PER_PIXEL = 128
LOCAL_SOLVER_BYTES_PER_PIXEL = 384


def base_bytes(shape):
    h, w = shape
    # Source RGB, current and next full tensor, one resampled weight, interpolation,
    # legacy float coverage and global nonzero indices, output conversion. Mapping
    # only one operation at a time avoids N full-frame weights being retained.
    return FIXED_BYTES + h*w*FULL_BYTES_PER_PIXEL


def _area(box):
    return 0 if box is None else (box[1]-box[0])*(box[3]-box[2])


def _patch_box(shape, recipe):
    """Upper bound the real patch context without allocating selection masks."""
    from .ops.source_patch import check_recipe
    p = check_recipe(recipe); h, w = shape
    points = p['polygon']
    # Same 1/16-pixel polygon convention and +/- raster border as _plan. Actual
    # nonzero selection is a subset; its .6*size+4 pad cannot exceed this bound.
    x0 = max(0, math.floor(min(x for x, y in points)*w)-2)
    x1 = min(w, math.ceil(max(x for x, y in points)*w)+3)
    y0 = max(0, math.floor(min(y for x, y in points)*h)-2)
    y1 = min(h, math.ceil(max(y for x, y in points)*h)+3)
    size = max(y1-y0, x1-x0, 4)
    pad = math.ceil(size*.6)+4
    return max(0,y0-pad), min(h,y1+pad), max(0,x0-pad), min(w,x1+pad)


def requirement(shape, op):
    """Read actual operation geometry/coverage, without changing its arithmetic."""
    if op.kind == 'clone_stamp':
        from .ops.clone_stamp import raster_plan
        box = raster_plan(shape, op.params)[2]
        # Full source/output are above; tile temporaries are covered by fixed128MiB.
        local = _area(box)*8
    elif op.kind == 'heal_vector':
        from .ops.heal_vector import raster_plan
        box = raster_plan(shape, op.params)[2]
        local = _area(box)*LOCAL_SOLVER_BYTES_PER_PIXEL
    elif op.kind == 'source_patch':
        local = _area(_patch_box(shape, op.params))*LOCAL_SOLVER_BYTES_PER_PIXEL
    elif op.kind == 'heal':
        from .ops.inpaint import mask_bbox
        from .repair_record import DEFAULT_REPAIR
        box = mask_bbox(op.weight, pad=int(op.params.get('pad', DEFAULT_REPAIR['pad'])),
                        grow=float(op.params.get('grow', DEFAULT_REPAIR['grow'])))
        local = _area(box)*LOCAL_SOLVER_BYTES_PER_PIXEL
    else:
        raise ValueError('Unknown repair cannot receive a native crop memory admission')
    return base_bytes(shape) + local


def admit(shape, budget, op=None):
    needed = base_bytes(shape) if op is None else requirement(shape, op)
    if type(budget) is not int or needed > budget:
        raise ValueError('Full-source eye repair phase/ROI exceeds memory admission; no proxy or reduced context')
    return needed
