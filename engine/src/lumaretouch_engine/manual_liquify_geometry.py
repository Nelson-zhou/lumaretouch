"""Invert only crop/rotation, not auto/manual warp: gestures address final canvas.

An already deformed feature is picked where it is currently rendered. Replaying
this destination-domain gesture composes onto the existing inverse mapping.
"""
import math
from copy import deepcopy
from .ops import geometry as G
from .manual_liquify_state import stroke


def inverse_stroke(capture, value):
    spec, valid = capture['spec'], capture['valid']
    xa, ya, xb, yb = spec.integer_crop
    cw, ch = xb-xa, yb-ya
    rw, rh = spec.rotated
    k = G._snapped_quarter_turn(spec.rotation)
    ca, sa = math.cos(math.radians(-spec.rotation)), math.sin(math.radians(-spec.rotation))
    def inverse(p):
        rx, ry = p[0]*rw-.5, p[1]*rh-.5
        if k == 0: x, y = rx, ry
        elif k == 1: x, y = ry, ch-1-rx
        elif k == 2: x, y = cw-1-rx, ch-1-ry
        elif k == 3: x, y = cw-1-ry, rx
        else:
            ux, uy = rx-(rw-1)/2, ry-(rh-1)/2
            x, y = ca*ux-sa*uy+(cw-1)/2, sa*ux+ca*uy+(ch-1)/2
        return [(x+xa+.5)/spec.width, (y+ya+.5)/spec.height]
    result = deepcopy(value)
    origin = inverse([0, 0])
    result['axes'] = [[v-origin[i] for i, v in enumerate(inverse(axis))] for axis in value['axes']]
    points = []
    for p in value['points']:
        ix, iy = p[0]*spec.width-.5, p[1]*spec.height-.5
        xs = [max(0, min(spec.width-1, int(f(ix)))) for f in (math.floor, math.ceil)]
        ys = [max(0, min(spec.height-1, int(f(iy)))) for f in (math.floor, math.ceil)]
        if not all(valid[y, x] for y in ys for x in xs):
            raise ValueError('液化笔迹中心落在旋转补边，已取消本笔')
        q = inverse(p)
        if any(v < -1e-12 or v > 1+1e-12 for v in q):
            raise ValueError('液化笔迹中心超出源画布')
        points.append([min(1., max(0., q[0])), min(1., max(0., q[1])), *p[2:]])
    result['points'] = points
    return stroke(result)
