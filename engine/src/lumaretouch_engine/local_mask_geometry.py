"""Invert capture control geometry with the exact Projection crop/rotate rule.

The reviewed capture must depict immutable source RGB. This module does not infer
coordinates from a deformed/retouched view. Parent controller owns capture/source
identity validation and rejects stale requests before calling this helper.
"""
import math

import numpy as np

from .ops import geometry as G
from .local_mask_recipe import DOMAIN, VERSION, check_object, raster, validate_budget


def inverse_object(spec, obj, valid, full_source):
    """Map one capture-normalized geometry object to an editable source object.

    full_source is (width,height). valid is the capture's actual H×W coverage
    boolean array. Metadata-only edits must not pass through this inverse twice.
    Linear/radial fields may continue beyond the cropped viewport; their control
    anchors must be genuine source pixels. Brush swept coverage must be genuine.
    """
    displayed = check_object(obj)
    if (not isinstance(valid, np.ndarray) or valid.shape != (spec.height, spec.width)
            or valid.dtype != np.bool_):
        raise ValueError('Local mask capture validity is unavailable')
    if (not isinstance(full_source, (list, tuple)) or len(full_source) != 2
            or any(type(n) is not int or n < 1 for n in full_source)):
        raise ValueError('Local mask full-resolution source dimensions are unavailable')
    xa, ya, xb, yb = spec.integer_crop
    cw, ch = xb-xa, yb-ya
    rw, rh = spec.rotated
    k = G._snapped_quarter_turn(spec.rotation)
    ca, sa = math.cos(math.radians(-spec.rotation)), math.sin(math.radians(-spec.rotation))

    def inverse(point):
        # The capture is rotated output resized to original proxy dimensions,
        # align_corners=False. Normalized edges eliminate that resize scale.
        rx, ry = point[0]*rw-.5, point[1]*rh-.5
        if k == 0:
            x, y = rx, ry
        elif k == 1:
            x, y = ry, ch-1-rx
        elif k == 2:
            x, y = cw-1-rx, ch-1-ry
        elif k == 3:
            x, y = cw-1-ry, rx
        else:
            ux, uy = rx-(rw-1)/2, ry-(rh-1)/2
            x, y = ca*ux-sa*uy+(cw-1)/2, sa*ux+ca*uy+(ch-1)/2
        return [(x+xa+.5)/spec.width, (y+ya+.5)/spec.height]

    origin = inverse([0, 0])

    def vector(value):
        endpoint = inverse(value)
        return [endpoint[i]-origin[i] for i in (0, 1)]

    def anchor(point):
        x, y = point[0]*spec.width-.5, point[1]*spec.height-.5
        ix = [max(0, min(spec.width-1, int(f(x)))) for f in (math.floor, math.ceil)]
        iy = [max(0, min(spec.height-1, int(f(y)))) for f in (math.floor, math.ceil)]
        if not all(valid[py, px] for py in iy for px in ix):
            raise ValueError('Local mask control point crosses rotation padding')
        result = inverse(point)
        # Floating arithmetic at exact source boundaries is allowed only at
        # machine epsilon, not a silent clamp of outside-source gestures.
        if any(v < -1e-12 or v > 1+1e-12 for v in result):
            raise ValueError('Local mask control point falls outside the source')
        return [min(1., max(0., v)) for v in result]

    kind = displayed['kind']
    mapped = dict(displayed)
    if kind == 'brush':
        mapped['points'] = [anchor(p) for p in displayed['points']]
        mapped['axes'] = [vector(a) for a in displayed['axes']]
        # Use the same Rust swept ellipse/feather, not a separate approximate
        # bounds test. Opacity cannot conceal a stroke through padding.
        coverage = raster(dict(version=VERSION, domain=DOMAIN,
                               objects=[dict(displayed, enabled=True, operation='add', opacity=1.)]),
                          (spec.height, spec.width))
        if not np.any(coverage):
            raise ValueError('Local mask brush covers no captured pixels')
        if np.any((coverage > 0) & ~valid):
            raise ValueError('Local mask brush crosses rotation padding')
    elif kind == 'linear':
        mapped.update(start=anchor(displayed['start']), end=anchor(displayed['end']),
                      cross=vector(displayed['cross']))
    elif kind == 'radial':
        mapped.update(center=anchor(displayed['center']), axes=[vector(a) for a in displayed['axes']])
    mapped = check_object(mapped)
    validate_budget(dict(version=VERSION, domain=DOMAIN, objects=[mapped]),
                    (full_source[1], full_source[0]))
    return mapped
