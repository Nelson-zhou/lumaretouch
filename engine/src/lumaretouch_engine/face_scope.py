"""Conservative selected-face mask construction, not an instance neural network.

Geometry uses the official MediaPipe FaceLandmarker topology. Semantic confidence
and geometry are intersected (as in exclusive mask composition), never unioned.
This module is a foundation; it does not itself implement per-person edit recipes.
"""
from __future__ import annotations
import numpy as np
from .ops.enhance import EYE_RING_LEFT, EYE_RING_RIGHT, LIP_CHAIN_UPPER, LIP_CHAIN_LOWER

# Google MediaPipe face_landmarks_connections.ts, FACE_LANDMARKS_FACE_OVAL.
FACE_OVAL = (10,338,297,332,284,251,389,356,454,323,361,288,397,365,379,378,
             400,377,152,148,176,149,150,136,172,58,132,93,234,127,162,21,54,103,67,109)
# Close the two official eyebrow chains into exclusion polygons.
BROW_LEFT = (276,283,282,295,285,336,296,334,293,300)
BROW_RIGHT = (46,53,52,65,55,107,66,105,63,70)
LIPS = LIP_CHAIN_UPPER + tuple(reversed(LIP_CHAIN_LOWER[1:-1]))


def _polygon_field(xs, ys, vertices):
    """Even/odd interior and exact nearest-segment distance, bounded ROI arrays."""
    p = np.asarray(vertices, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != 2 or len(p) < 3 or not np.isfinite(p).all():
        raise ValueError('face region requires a finite polygon')
    nxt = np.roll(p, -1, axis=0)
    area = abs(np.sum(p[:,0]*nxt[:,1] - nxt[:,0]*p[:,1])) / 2
    if area < .25:
        raise ValueError('face region is degenerate at this image resolution')
    inside = np.zeros(np.broadcast_shapes(xs.shape, ys.shape), dtype=bool)
    distance2 = np.full(inside.shape, np.inf)
    for a,b in zip(p,nxt):
        dx,dy = b-a
        length2 = dx*dx+dy*dy
        if length2 < 1e-12: continue
        t = np.clip(((xs-a[0])*dx+(ys-a[1])*dy)/length2,0,1)
        distance2 = np.minimum(distance2,(xs-a[0]-t*dx)**2+(ys-a[1]-t*dy)**2)
        if abs(dy)>1e-12:
            crosses = ((a[1]>ys)!=(b[1]>ys)) & (xs < (ys-a[1])*dx/dy+a[0])
            inside ^= crosses
    distance = np.sqrt(distance2)
    inside |= distance <= 1e-7
    return inside,distance


def selected_face_skin(semantic_weight, landmarks, *, other_landmarks=()):
    """Intersect trusted face-skin weight with one face, excluding eyes/lips/brows.

    semantic_weight must be the validated face-skin class's editing confidence,
    not the whole-person or body-skin mask. Outside the selected oval is exactly
    zero. Feature interiors and other face ovals are exactly zero, with outward
    protection feather. Overlap is conservatively excluded, not identity-guessed.
    Invalid or subpixel geometry raises rather than producing a global fallback.
    """
    weight=np.asarray(semantic_weight,dtype=np.float32)
    if weight.ndim!=2 or not weight.size or not np.isfinite(weight).all() or np.any((weight<0)|(weight>1)):
        raise ValueError('face-skin editing weight must be finite HxW in [0,1]')
    h,w=weight.shape
    def pixels(lm):
        a=np.asarray(lm,dtype=np.float64)
        if a.shape!=(478,3) or not np.isfinite(a).all():
            raise ValueError('selected face requires finite 478x3 landmarks')
        return a[:,:2]*np.array([w,h],dtype=np.float64)
    pts=pixels(landmarks);oval=pts[list(FACE_OVAL)]
    span=float(np.max(np.ptp(oval,axis=0)))
    if span < 4: raise ValueError('selected face is too small for a reliable mask')
    feather=max(1.0,span*.015)
    x0,y0=np.maximum(np.floor(oval.min(axis=0)).astype(int),0)
    x1,y1=np.minimum(np.ceil(oval.max(axis=0)).astype(int)+1,[w,h])
    result=np.zeros_like(weight)
    if x1<=x0 or y1<=y0: return result
    xs=np.arange(x0,x1,dtype=np.float64)[None,:]+.5
    ys=np.arange(y0,y1,dtype=np.float64)[:,None]+.5
    inside,dist=_polygon_field(xs,ys,oval)
    scope=inside*np.clip(dist/feather,0,1)
    # Protect the entire pixel footprint at feature edges, not only its center.
    # Half a pixel diagonal is the maximum center-to-corner distance.
    for ids in (EYE_RING_LEFT,EYE_RING_RIGHT,LIPS,BROW_LEFT,BROW_RIGHT):
        interior,distance=_polygon_field(xs,ys,pts[list(ids)])
        scope*=np.where(interior,0,np.clip((distance-np.sqrt(.5))/feather,0,1))
    for other in other_landmarks:
        interior,distance=_polygon_field(xs,ys,pixels(other)[list(FACE_OVAL)])
        scope*=np.where(interior,0,np.clip((distance-np.sqrt(.5))/feather,0,1))
    result[y0:y1,x0:x1]=weight[y0:y1,x0:x1]*scope
    return np.ascontiguousarray(result)
