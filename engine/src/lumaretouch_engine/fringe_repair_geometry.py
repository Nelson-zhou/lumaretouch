"""Fringe gestures address the edited, post-optics canvas before crop/rotation.

Source binding is ownership, not immutable-source mask geometry. Never transport
these strokes through face/body deformation, manual liquify or optics a second
time. Only the exact final crop/rotation is inverted or applied here.
"""
from copy import deepcopy
import math

from .ops import geometry as G


def _projection(source_size, geometry):
    if (not isinstance(source_size, (tuple, list)) or len(source_size) != 2
            or any(type(v) is not int or v < 1 or v > 65536 for v in source_size)):
        raise ValueError('Fringe coverage requires verified full-source dimensions')
    width, height = source_size
    rect, angle = geometry or ((0., 0., 1., 1.), 0.)
    x0, y0, x1, y1, angle = G.check(rect, angle)
    xa, xb = G._cut(width, x0, x1)
    ya, yb = G._cut(height, y0, y1)
    cw, ch = xb - xa, yb - ya
    ow, oh = G.out_size(width, height, rect, angle)
    quarter = G._snapped_quarter_turn(angle)
    ca, sa = math.cos(math.radians(-angle)), math.sin(math.radians(-angle))

    def inverse(point, *, anchor=False):
        # UI coordinates are normalized edges of the displayed final canvas.
        # Full-size crop rounding is authoritative, never proxy crop rounding.
        rx, ry = point[0] * ow - .5, point[1] * oh - .5
        if quarter == 0:
            x, y = rx, ry
        elif quarter == 1:
            x, y = ry, ch - 1 - rx
        elif quarter == 2:
            x, y = cw - 1 - rx, ch - 1 - ry
        elif quarter == 3:
            x, y = cw - 1 - ry, rx
        else:
            dx, dy = rx - (ow - 1) / 2., ry - (oh - 1) / 2.
            x, y = ca * dx - sa * dy + (cw - 1) / 2., sa * dx + ca * dy + (ch - 1) / 2.
        if anchor:
            # Same real-pixel support rule as photo_grain_geometry.mapping.
            if quarter is None:
                valid = (-.5 <= x <= cw - .5 and -.5 <= y <= ch - .5) if min(cw, ch) == 1 else (0 <= math.floor(x) < cw - 1 and 0 <= math.floor(y) < ch - 1)
            else:
                valid = -.5 <= x <= cw - .5 and -.5 <= y <= ch - .5
            if not valid:
                raise ValueError('Fringe brush anchor crosses crop/rotation padding')
        return [(x + xa + .5) / width, (y + ya + .5) / height]
    return inverse, (ow, oh)


def inverse_strokes(source_size, geometry, raw_ui_strokes):
    """Validate new display-domain gestures, then invert crop/rotation once.

    The UI sends circles whose radius is a fraction of the final canvas's short
    edge. Convert them to display-normalized basis vectors before the affine
    inverse. Existing retained ellipses must never pass through here again.
    """
    from .fringe_repair_state import check_stroke, number, MAX_POINTS
    if type(raw_ui_strokes) is not list or len(raw_ui_strokes) > 128:
        raise ValueError('Fringe gesture list exceeds the bounded stroke budget')
    inverse, (ow, oh) = _projection(source_size, geometry)
    origin = inverse([0., 0.])
    result = []
    total_points = 0
    for raw in raw_ui_strokes:
        if type(raw) is not dict or set(raw) != {'id', 'mode', 'points', 'radius', 'opacity', 'feather'}:
            raise ValueError('Fringe display gesture requires complete circular brush intent')
        radius = number(raw['radius'], 0., .5, 'display brush radius')
        if radius <= 0.:
            raise ValueError('Fringe display brush radius must be positive')
        circle = dict(raw)
        circle.pop('radius')
        pixels = radius * min(ow, oh)
        circle['axes'] = [[pixels / ow, 0.], [0., pixels / oh]]
        stroke = check_stroke(circle)
        total_points += len(stroke['points'])
        if total_points > MAX_POINTS:
            raise ValueError('Fringe gesture list exceeds the total point budget')
        mapped = deepcopy(stroke)
        mapped['points'] = [inverse(point, anchor=True) for point in stroke['points']]
        mapped['axes'] = [[v - origin[i] for i, v in enumerate(inverse(axis))] for axis in stroke['axes']]
        result.append(check_stroke(mapped))
    if len({row['id'] for row in result}) != len(result):
        raise ValueError('Fringe gesture identities must be unique')
    return result


def coverage(recipe, source_size, geometry, canvas_size, *, cancelled=lambda: False):
    """Rasterize retained vectors at full size; crop validity is applied last.

    Initial coverage is one. Erase excludes automatic repair, while add restores
    eligibility. Neither gesture bypasses the Rust halo detector or its guide.
    The existing Rust swept-ellipse/feather rasterizer owns brush geometry; its
    uint8 output is a full-resolution vector raster, never a resized proxy mask.
    """
    import numpy as np
    from . import fringe_repair_state as S, local_mask_recipe as R
    from .photo_grain_geometry import mapping
    value = S.check(recipe)
    _, expected = _projection(source_size, geometry)
    if tuple(canvas_size) != expected:
        raise ValueError('Fringe repair requires the full-resolution geometry canvas')
    width, height = source_size
    strokes = value['coverage']['strokes']
    plans = []
    total_work = 0
    for index, stroke in enumerate(strokes):
        obj = dict(id='fringe_' + str(index), name='Fringe eligibility', enabled=True,
                   operation='add', kind='brush', opacity=stroke['opacity'],
                   feather=stroke['feather'] * 100., points=stroke['points'], axes=stroke['axes'])
        stack = dict(version=R.VERSION, domain=R.DOMAIN, objects=[obj])
        plan = R.validate_budget(stack, (height, width))
        total_work += plan['work'] + width * height
        if total_work > R.MAX_WORK:
            raise ValueError('Fringe coverage exceeds the full-resolution vector work budget')
        plans.append((stroke['mode'], stack))
    if cancelled():
        raise InterruptedError('Fringe coverage cancelled')
    field = np.ones((height, width), np.float32)
    for mode, stack in plans:
        if cancelled():
            raise InterruptedError('Fringe coverage cancelled')
        dab = R.raster(stack, (height, width)).astype(np.float32) / 255.
        if mode == 'subtract':
            field *= 1. - dab
        else:
            field += (1. - field) * dab
    rect, angle = geometry or ((0., 0., 1., 1.), 0.)
    field = G.crop_rotate_np(field[..., None], rect, angle, uint8=False)[..., 0]
    field = np.array(field, dtype=np.float32, order='C', copy=True)
    mapper = mapping(tuple(source_size), geometry, tuple(canvas_size))
    for y in range(field.shape[0]):
        if y % 64 == 0 and cancelled():
            raise InterruptedError('Fringe coverage cancelled')
        field[y] *= mapper(0, y, field.shape[1])[:, 2]
    if not np.isfinite(field).all() or np.any(field < 0) or np.any(field > 1):
        raise ValueError('Fringe coverage is not finite normalized eligibility')
    return field
