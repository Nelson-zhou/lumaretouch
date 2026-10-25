# SPDX-License-Identifier: GPL-3.0-or-later
"""Measured native face crops and source-owned editable fusion coverage.

The oval is geometry, not skin segmentation or an occlusion detector. Known
semantic exclusions and every other measured face veto pixels; the user must
still review unknown occlusion. No full-resolution semantic precision is claimed
for measured proxy masks resampled to this exact source coordinate domain.
"""
import math
import numpy as np
from . import people_state as P
from .face_scope import FACE_OVAL, _polygon_field

MAX_CROP_EDGE = 1024
MAX_STROKES = 128
MAX_POINTS = 2048


def _number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('Expression geometry is outside finite source bounds')
    return float(value)


def face_crop(capture, ref, *, cancelled=lambda:False):
    if cancelled():raise InterruptedError('Expression crop preparation cancelled')
    ref = P.check_ref(ref)
    face = capture.graph['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref or not face['enabled'] or face['manual']:
        raise ValueError('Expression face is not the exact enabled measured source instance')
    row = capture.analyses.get(ref['face_instance_id'])
    if row is None or row['face_ref'] != ref or row['evidence'] != face['evidence']:
        raise ValueError('Expression landmarks do not belong to the selected source face')
    width, height = capture.source['width'], capture.source['height']
    points = np.asarray(row['landmarks'], dtype=np.float64)
    if points.shape != (478, 3) or not np.isfinite(points).all():
        raise ValueError('Expression requires all real 478 landmarks')
    # MediaPipe normalized image coordinates refer to the full image extent.
    # Convert once to integer-centred source pixels before crop endpoint ABI.
    xy = points[:, :2] * [width, height] - .5
    oval = xy[list(FACE_OVAL)]
    lo, hi = oval.min(0), oval.max(0)
    span = hi-lo
    if min(span) < 64:
        raise ValueError('Expression face is too small for defensible source blending')
    pad = max(16., float(max(span))*.15)
    left, top = np.floor(lo-pad).astype(int)
    right, bottom = np.ceil(hi+pad+1).astype(int)
    if left < 0 or top < 0 or right > width or bottom > height:
        raise ValueError('Expression requires an unclipped actual face-context crop')
    w, h = int(right-left), int(bottom-top)
    if max(w, h) > MAX_CROP_EDGE:
        raise ValueError('Native face context exceeds 1024 pixels; no resizing to pretend full-resolution support')
    xx = np.arange(left, right, dtype=np.float64)[None, :]
    yy = np.arange(top, bottom, dtype=np.float64)[:, None]
    allowed = np.empty((h,w),dtype=np.float32)
    for start in range(0,h,64):
        if cancelled():raise InterruptedError('Expression polygon raster cancelled')
        inside,distance=_polygon_field(xx,yy[start:start+64],oval)
        allowed[start:start+64]=np.where(inside,np.clip((distance-1.)/max(2.,min(span)*.025),0,1),0)
    protected = np.zeros((h, w), dtype=np.float32)
    for key, other in capture.graph['faces'].items():
        if cancelled():raise InterruptedError('Expression protected-face raster cancelled')
        if key == ref['face_instance_id']:
            continue
        box = np.asarray(other['box'], dtype=np.float64)*[width, height, width, height]
        margin = max(3., float(min(span))*.04)
        protected[((xx >= box[0]-margin)&(xx <= box[2]+margin))
                  &((yy >= box[1]-margin)&(yy <= box[3]+margin))] = 1
    exclusion = row.get('excluded')
    if exclusion is not None:
        observed = np.asarray(exclusion, dtype=np.float32)
        if observed.shape != capture.proxy.shape[:2] or not np.isfinite(observed).all():
            raise ValueError('Expression exclusions lack the captured source grid')
        # Source-normalized centre mapping, not a rescaled UI brush bitmap.
        px = np.clip(((xx+.5)*observed.shape[1]/width-.5).round().astype(int),0,observed.shape[1]-1)
        py = np.clip(((yy+.5)*observed.shape[0]/height-.5).round().astype(int),0,observed.shape[0]-1)
        protected[observed[py, px] > 0] = 1
    allowed[protected > 0] = 0
    if not np.any(allowed > 0):
        raise ValueError('No measured unprotected face coverage remains')
    landmarks = points.copy()
    landmarks[:, :2] = (xy-[left, top])/[w-1, h-1]
    # MediaPipe z is normalized in original image-width units. A native crop
    # changes that unit, not the underlying measured depth values.
    landmarks[:, 2] *= width/(w-1)
    rgba = np.frombuffer(capture.asset['content'], dtype='<f4').reshape(height, width, 4)
    crop = np.ascontiguousarray(rgba[top:bottom, left:right], dtype=np.float32)
    landmarks = np.ascontiguousarray(landmarks, dtype=np.float32)
    for array in (crop, landmarks, allowed, protected):
        array.setflags(write=False)
    return {'left': int(left), 'top': int(top), 'width': w, 'height': h}, crop, landmarks, allowed, protected


def fusion_mask(value, crop, source, allowed, *, cancelled=lambda: False):
    """Explicit empty initial selection, source-normalized pixel-centre strokes."""
    if (type(value) is not dict or set(value) != {'version','coordinates','initial','strokes'}
            or value['version'] != 1 or value['coordinates'] != 'source_normalized_pixel_centres'
            or value['initial'] != 'empty' or type(value['strokes']) is not list
            or len(value['strokes']) > MAX_STROKES):
        raise ValueError('Expression fusion requires explicit bounded source-owned strokes')
    h, w = allowed.shape
    xx = np.arange(crop['left'], crop['left']+w, dtype=np.float64)[None, :]
    yy = np.arange(crop['top'], crop['top']+h, dtype=np.float64)[:, None]
    result = np.zeros((h, w), dtype=np.float32)
    count = 0
    for stroke in value['strokes']:
        if cancelled(): raise InterruptedError('Expression fusion raster cancelled')
        if type(stroke) is not dict or set(stroke) != {'mode','radius_px','points'} or stroke['mode'] not in ('add','erase'):
            raise ValueError('Unknown expression fusion brush')
        radius = _number(stroke['radius_px'], 1, 512)
        points = stroke['points']
        if type(points) is not list or not points:
            raise ValueError('Expression fusion stroke is empty')
        count += len(points)
        if count > MAX_POINTS: raise ValueError('Expression fusion point budget exceeded')
        coords=[]
        for point in points:
            if type(point) is not list or len(point) != 2: raise ValueError('Invalid source stroke point')
            coords.append(np.array([_number(point[0],0,1)*(source['width']-1),
                                    _number(point[1],0,1)*(source['height']-1)]))
        coverage = np.zeros((h,w), dtype=np.float32)
        for a,b in zip(coords, coords[1:] or coords):
            if cancelled(): raise InterruptedError('Expression fusion raster cancelled')
            delta=b-a; length=float(delta@delta)
            t=np.clip(((xx-a[0])*delta[0]+(yy-a[1])*delta[1])/max(length,1e-20),0,1)
            distance=np.hypot(xx-a[0]-t*delta[0],yy-a[1]-t*delta[1])
            coverage=np.maximum(coverage,np.clip((radius-distance)/max(1.,radius*.25),0,1))
        result=np.maximum(result,coverage) if stroke['mode']=='add' else result*(1-coverage)
    result=np.ascontiguousarray(np.minimum(result,allowed), dtype=np.float32)
    result.setflags(write=False)
    return result
