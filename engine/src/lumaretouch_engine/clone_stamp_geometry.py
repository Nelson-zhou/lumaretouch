"""Map a reviewed capture stroke through its exact crop/rotate affine transform."""
import math
import numpy as np
from .ops import geometry as G
from .ops.clone_stamp import VERSION, MAX_POINTS, number, pair, check_recipe, raster, raster_plan


def inverse_stroke(spec, stroke, valid, full_source):
    if type(stroke) is not dict or set(stroke) != {'points', 'source', 'size', 'hardness', 'opacity'}:
        raise ValueError('Invalid clone stroke fields')
    if not isinstance(stroke['points'], (list, tuple)) or not 1 <= len(stroke['points']) <= MAX_POINTS:
        raise ValueError('Clone stroke requires 1–1024 points')
    points = [pair(p) for p in stroke['points']]
    source = pair(stroke['source'])
    size = number(stroke['size'])
    if not .001 <= size <= 1:
        raise ValueError('Clone brush diameter must be in [0.001, 1]')
    radius = size*min(spec.width, spec.height)/2
    offset = [source[i]-points[0][i] for i in (0, 1)]
    displayed = check_recipe(dict(version=VERSION, points=points, offset=offset,
        axes=[[radius/spec.width, 0], [0, radius/spec.height]],
        hardness=stroke['hardness'], opacity=stroke['opacity']))
    mask, (y0, y1, x0, x1) = raster((spec.height, spec.width), {**displayed, 'opacity': 1.0})
    if not np.any(mask):
        raise ValueError('Clone stroke covers no pixels')
    dx, dy = offset[0]*spec.width, offset[1]*spec.height
    # Prove the *whole swept footprint*, not just pointer centers, is genuine
    # captured image content. Both bilinear donor neighbours must be valid.
    for ya in range(y0, y1, 128):
        yb = min(y1, ya+128)
        selected = mask[ya-y0:yb-y0] > 0
        if np.any(selected & ~valid[ya:yb, x0:x1]):
            raise ValueError('Clone target crosses rotation padding')
        sy = np.arange(ya, yb, dtype=np.float64)+dy
        sx = np.arange(x0, x1, dtype=np.float64)+dx
        inside = (sy[:, None] >= 0)&(sy[:, None] <= spec.height-1)&(sx[None, :] >= 0)&(sx[None, :] <= spec.width-1)
        if np.any(selected & ~inside):
            raise ValueError('Clone source footprint crosses the image boundary')
        iy = np.clip(np.floor(sy).astype(np.int64), 0, spec.height-1)
        ix = np.clip(np.floor(sx).astype(np.int64), 0, spec.width-1)
        jy = np.clip(np.ceil(sy).astype(np.int64), 0, spec.height-1)
        jx = np.clip(np.ceil(sx).astype(np.int64), 0, spec.width-1)
        donor = valid[iy[:, None], ix[None, :]] & valid[iy[:, None], jx[None, :]] & valid[jy[:, None], ix[None, :]] & valid[jy[:, None], jx[None, :]]
        if np.any(selected & ~donor):
            raise ValueError('Clone source footprint crosses rotation padding')
    xa, ya, xb, yb = spec.integer_crop
    cw, ch = xb-xa, yb-ya
    rw, rh = spec.rotated
    k = G._snapped_quarter_turn(spec.rotation)
    ca, sa = math.cos(math.radians(-spec.rotation)), math.sin(math.radians(-spec.rotation))
    def inverse(point):
        rx, ry = point[0]*rw-.5, point[1]*rh-.5
        if k == 0: x, y = rx, ry
        elif k == 1: x, y = ry, ch-1-rx
        elif k == 2: x, y = cw-1-rx, ch-1-ry
        elif k == 3: x, y = cw-1-ry, rx
        else:
            ux, uy = rx-(rw-1)/2, ry-(rh-1)/2
            x, y = ca*ux-sa*uy+(cw-1)/2, sa*ux+ca*uy+(ch-1)/2
        return [(x+xa+.5)/spec.width, (y+ya+.5)/spec.height]
    origin = inverse([0, 0])
    axes = [[inverse(axis)[i]-origin[i] for i in (0, 1)] for axis in displayed['axes']]
    mapped = [inverse(p) for p in points]
    donor = inverse(source)
    recipe = check_recipe(dict(version=VERSION, points=mapped,
        offset=[donor[i]-mapped[0][i] for i in (0, 1)], axes=axes,
        hardness=displayed['hardness'], opacity=displayed['opacity']))
    if (not isinstance(full_source, (list, tuple)) or len(full_source) != 2
            or any(type(n) is not int or n < 1 for n in full_source)):
        raise ValueError('Clone full-resolution source dimensions are unavailable')
    # Reject an export-inadmissible stroke before committing its proxy. Planning
    # uses the identical footprint bounds/work count, with only O(points) memory.
    raster_plan((full_source[1], full_source[0]), recipe)
    coverage, box = raster((spec.height, spec.width), recipe)
    weight = np.zeros((spec.height, spec.width), np.uint8)
    y0, y1, x0, x1 = box
    # Diagnostic/history coverage only. Actual proxy and export masks are float
    # re-rasterizations of the same vector recipe, never this quantized array.
    weight[y0:y1, x0:x1] = np.ceil(coverage*255).astype(np.uint8)
    return recipe, weight
