"""Versioned color-and-texture clone brush, sampled from the pre-stroke base.

One stroke is a continuous swept ellipse with non-accumulating opacity. The
vector recipe, not its proxy coverage, is rasterized for full-resolution replay.
No source pixels are changed until the entire stroke has been computed.
"""
import math
import numpy as np

VERSION = 'clone-stamp-v1'
MAX_POINTS = 1024
MAX_ROI = 16_000_000
MAX_RASTER_WORK = 256_000_000


def number(value):
    if type(value) not in (int, float):
        raise ValueError('Clone brush requires finite numbers')
    try:
        value = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError('Clone brush requires finite numbers') from error
    if not math.isfinite(value):
        raise ValueError('Clone brush requires finite numbers')
    return value


def pair(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('Clone brush requires coordinate pairs')
    return [number(v) for v in value]


def check_recipe(raw):
    if type(raw) is not dict or set(raw) != {'version', 'points', 'offset', 'axes', 'hardness', 'opacity'} or raw['version'] != VERSION:
        raise ValueError('Unsupported clone-stamp recipe')
    if not isinstance(raw['points'], (list, tuple)) or not 1 <= len(raw['points']) <= MAX_POINTS:
        raise ValueError('Clone stroke requires 1–1024 points')
    points = [pair(p) for p in raw['points']]
    offset = pair(raw['offset'])
    if any(not 0 <= v <= 1 for p in points for v in p) or any(not -1 <= v <= 1 for v in offset):
        raise ValueError('Clone coordinates exceed the image')
    if any(not 0 <= p[i] + offset[i] <= 1 for p in points for i in (0, 1)):
        raise ValueError('Clone source path exceeds the image')
    if not isinstance(raw['axes'], (list, tuple)) or len(raw['axes']) != 2:
        raise ValueError('Invalid clone brush axes')
    axes = [pair(a) for a in raw['axes']]
    determinant = axes[0][0]*axes[1][1]-axes[0][1]*axes[1][0]
    if abs(determinant) < 1e-14 or any(abs(v) > 1 for a in axes for v in a):
        raise ValueError('Degenerate or oversized clone brush')
    hardness, opacity = number(raw['hardness']), number(raw['opacity'])
    if not 0 <= hardness <= 1 or not 0 <= opacity <= 1:
        raise ValueError('Clone hardness/opacity is outside its range')
    return dict(version=VERSION, points=points, offset=offset, axes=axes, hardness=hardness, opacity=opacity)


def raster_plan(shape, recipe):
    """Admit all image/ROI/work bounds without allocating a raster."""
    p = check_recipe(recipe)
    h, w = shape
    if h < 1 or w < 1 or h*w > 120_000_000:
        raise ValueError('Clone input exceeds the image budget')
    points = np.asarray(p['points'], np.float64)*[w, h]-.5
    basis = np.asarray(p['axes'], np.float64).T*np.asarray([[w], [h]])
    inverse = np.linalg.inv(basis)
    ex, ey = np.sqrt(np.sum(basis*basis, axis=1))
    x0 = max(0, math.floor(points[:, 0].min()-ex))
    x1 = min(w, math.ceil(points[:, 0].max()+ex)+1)
    y0 = max(0, math.floor(points[:, 1].min()-ey))
    y1 = min(h, math.ceil(points[:, 1].max()+ey)+1)
    if x1 <= x0 or y1 <= y0 or (x1-x0)*(y1-y0) > MAX_ROI:
        raise ValueError('Clone stroke exceeds the local raster budget')
    work = 0
    planned = []
    segments = zip(points, points[1:]) if len(points) > 1 else [(points[0], points[0])]
    for a, b in segments:
        xa = max(x0, math.floor(min(a[0], b[0])-ex))
        xb = min(x1, math.ceil(max(a[0], b[0])+ex)+1)
        ya = max(y0, math.floor(min(a[1], b[1])-ey))
        yb = min(y1, math.ceil(max(a[1], b[1])+ey)+1)
        work += (xb-xa)*(yb-ya)
        if work > MAX_RASTER_WORK:
            raise ValueError('Clone stroke is too complex; split it into shorter strokes')
        planned.append((a, b, ya, yb, xa, xb))
    return p, inverse, (y0, y1, x0, x1), planned


def raster(shape, recipe):
    """Rasterize admitted segments in 128×2048 tiles, never segment-size arrays."""
    p, inverse, box, planned = raster_plan(shape, recipe)
    y0, y1, x0, x1 = box
    alpha = np.zeros((y1-y0, x1-x0), np.float32)
    for a, b, ya, yb, xa, xb in planned:
        delta = inverse@(b-a)
        length = float(delta@delta)
        hardness = p['hardness']
        for ty in range(ya, yb, 128):
            ey = min(yb, ty+128)
            for tx in range(xa, xb, 2048):
                ex = min(xb, tx+2048)
                yy, xx = np.ogrid[ty:ey, tx:ex]
                ux = inverse[0, 0]*(xx-a[0])+inverse[0, 1]*(yy-a[1])
                uy = inverse[1, 0]*(xx-a[0])+inverse[1, 1]*(yy-a[1])
                t = np.clip((ux*delta[0]+uy*delta[1])/length, 0, 1) if length > 1e-20 else 0
                distance = np.sqrt((ux-t*delta[0])**2+(uy-t*delta[1])**2)
                coverage = (distance <= 1).astype(np.float32) if hardness == 1 else np.clip((1-distance)/(1-hardness), 0, 1).astype(np.float32)
                # Smooth edge, with opacity capped once across the whole gesture.
                if hardness != 1:
                    coverage *= coverage*(3-2*coverage)
                target = alpha[ty-y0:ey-y0, tx-x0:ex-x0]
                np.maximum(target, coverage*p['opacity'], out=target)
    return alpha, box


def apply_t(cur, recipe):
    """Read-only float32 source with ROI-only sampling, no baked display pixels."""
    import torch
    if not isinstance(cur, torch.Tensor) or cur.ndim != 4 or cur.shape[:2] != (1, 3) or cur.dtype != torch.float32:
        raise ValueError('Clone requires single float32 BCHW RGB')
    p = check_recipe(recipe)
    h, w = cur.shape[-2:]
    if p['opacity'] == 0:
        return cur.clone(), None
    mask, box = raster((h, w), p)
    y0, y1, x0, x1 = box
    if not np.any(mask):
        raise ValueError('Clone stroke covers no pixels')
    # Translation is fractional, preserving source geometry on proxy/full frames.
    dx, dy = p['offset'][0]*w, p['offset'][1]*h
    if dx == 0 and dy == 0:
        return cur.clone(), None
    out = cur.clone()
    for ya in range(y0, y1, 128):
        yb = min(y1, ya+128)
        for xa in range(x0, x1, 2048):
            xb = min(x1, xa+2048)
            alpha = torch.from_numpy(mask[ya-y0:yb-y0, xa-x0:xb-x0]).to(cur.device)
            yy = torch.arange(ya, yb, device=cur.device, dtype=torch.float64)+dy
            xx = torch.arange(xa, xb, device=cur.device, dtype=torch.float64)+dx
            valid = (yy[:, None] >= 0)&(yy[:, None] <= h-1)&(xx[None, :] >= 0)&(xx[None, :] <= w-1)
            if bool(torch.any((alpha > 0)&~valid)):
                raise ValueError('Clone source footprint exceeds image pixels')
            yy, xx = yy.clamp(0, h-1), xx.clamp(0, w-1)
            iy, ix = yy.floor().long(), xx.floor().long()
            jy, jx = (iy+1).clamp(max=h-1), (ix+1).clamp(max=w-1)
            fy, fx = (yy-iy).to(torch.float32)[:, None], (xx-ix).to(torch.float32)[None, :]
            source = ((cur[0, :, iy[:, None], ix[None, :]]*(1-fx)+cur[0, :, iy[:, None], jx[None, :]]*fx)*(1-fy)
                      +(cur[0, :, jy[:, None], ix[None, :]]*(1-fx)+cur[0, :, jy[:, None], jx[None, :]]*fx)*fy)
            target = cur[0, :, ya:yb, xa:xb]
            if not bool(torch.isfinite(source).all() and torch.isfinite(target).all()):
                raise ValueError('Clone input contains nonfinite pixels')
            # Exact outside preservation even when an unrelated source has bad pixels.
            result = torch.where(alpha[None] > 0, target+(source-target)*alpha[None], target)
            out[0, :, ya:yb, xa:xb] = result
    return out, box
