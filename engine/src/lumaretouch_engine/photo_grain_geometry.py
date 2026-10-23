"""Inverse mapping matching ops.geometry; no proxy-scale coordinate invention."""
import math
import numpy as np
from .ops.geometry import check, _cut, _snapped_quarter_turn, out_size


def mapping(source_size, geometry, canvas_size):
    w, h = source_size
    rect, angle = geometry or ((0., 0., 1., 1.), 0.)
    x0, y0, x1, y1, angle = check(rect, angle)
    xa, xb = _cut(w, x0, x1); ya, yb = _cut(h, y0, y1)
    cw, ch = xb-xa, yb-ya
    ow, oh = out_size(w, h, rect, angle)
    if canvas_size != (ow, oh):
        raise ValueError('Grain requires full-resolution geometry canvas, not resized pixels')
    k = _snapped_quarter_turn(angle)
    def row(x, y, n):
        xx = np.arange(x, x+n, dtype=np.float64)
        if k == 0: sx, sy = xx, np.full(n, y, dtype=np.float64)
        elif k == 1: sx, sy = np.full(n, y, dtype=np.float64), ch-1-xx
        elif k == 2: sx, sy = cw-1-xx, np.full(n, ch-1-y, dtype=np.float64)
        elif k == 3: sx, sy = np.full(n, cw-1-y, dtype=np.float64), xx
        else:
            a = math.radians(-angle); ca, sa = math.cos(a), math.sin(a)
            dx = xx-(ow-1)/2.; dy = y-(oh-1)/2.
            sx = ca*dx-sa*dy+(cw-1)/2.; sy = sa*dx+ca*dy+(ch-1)/2.
        valid = np.ones(n, dtype=bool)
        if k is None:
            if cw == 1 or ch == 1:
                valid = (sx >= -.5)&(sx <= cw-.5)&(sy >= -.5)&(sy <= ch-.5)
                sx = np.clip(sx,0,cw-1); sy = np.clip(sy,0,ch-1)
            else:
                valid = (np.floor(sx)>=0)&(np.floor(sx)<cw-1)&(np.floor(sy)>=0)&(np.floor(sy)<ch-1)
        coords = np.empty((n,3), dtype=np.float32)
        coords[:,0]=sx+xa;coords[:,1]=sy+ya;coords[:,2]=valid
        return coords
    return row
