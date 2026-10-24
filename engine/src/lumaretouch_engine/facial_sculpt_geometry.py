# SPDX-License-Identifier: GPL-3.0-or-later
"""Measured face topology is a conservative domain, never visibility evidence."""
import math
import numpy as np
from .face_scope import FACE_OVAL, BROW_LEFT, BROW_RIGHT, _polygon_field
from .lip_makeup_geometry import OUTER as LIPS, _crossed
from .ops.enhance import EYE_RING_LEFT, EYE_RING_RIGHT
MAX_PIXELS = 4_000_000


def mask(value, shape, label):
    if (type(value) is not np.ndarray or value.dtype != np.float32 or value.shape != tuple(shape)
            or not np.isfinite(value).all() or np.any((value < 0) | (value > 1))):
        raise ValueError('面部立体缺少当前来源的有效 ' + label)
    return value


def boxes(value):
    from .people_state import MAX_FACES
    if type(value) not in (list, tuple) or len(value) > MAX_FACES:
        raise ValueError('面部立体其他人物保护超过预算')
    for box in value:
        if (type(box) not in (list, tuple) or len(box) != 4
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)
                or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1)):
            raise ValueError('面部立体需要所有其他人物的规范来源框')
    return tuple(tuple(box) for box in value)


def geometry(landmarks, shape):
    h, w = shape
    p = np.asarray(landmarks, np.float64)[:, :2] * [w-1, h-1]
    if p.shape != (478, 2) or not np.isfinite(p).all():
        raise ValueError('面部立体需要真实完整 478 点分析')
    oval = p[list(FACE_OVAL)]
    if (_crossed(oval) or np.any(oval < 2) or np.any(oval[:, 0] > w-3)
            or np.any(oval[:, 1] > h-3)):
        raise ValueError('脸部被裁切或边界异常，面部立体暂不应用')
    axis = p[454] - p[234]
    width = float(np.linalg.norm(axis))
    eye = [float(np.linalg.norm(p[a]-p[b])) for a, b in ((33, 133), (263, 362))]
    halves = [float(np.linalg.norm(p[a]-p[1])) for a in (234, 454)]
    if width < 96 or min(eye) < 14 or min(eye) < .65*max(eye) or min(halves) < .65*max(halves):
        raise ValueError('人物过小或侧脸过强，面部立体暂不应用')
    right = axis/width
    down = np.array([-right[1], right[0]])
    if right[0] <= 0 or np.dot(p[152]-p[10], down) < .7*width:
        raise ValueError('面部立体纵向解剖支撑不可靠')
    radius = int(math.ceil(.025*width))
    if not 2 <= radius <= 128:
        raise ValueError('面部立体来源尺度超出专用内核范围；未缩放替代')
    lo = np.maximum(np.floor(oval.min(axis=0)-4*radius-2), 0).astype(int)
    hi = np.minimum(np.ceil(oval.max(axis=0)+4*radius+3), [w, h]).astype(int)
    x, y = map(int, lo); x1, y1 = map(int, hi)
    if (y1-y)*(x1-x) > MAX_PIXELS:
        raise ValueError('面部立体完整来源窗口超预算；未降采样')
    # These ellipses only bound editing zones, not a reconstructed 3D surface,
    # inferred hairline, cosmetic template or permission to touch invisible skin.
    zones = (
        ('forehead_center', (p[10]+p[151])*.5, .15*width, .12*width),
        ('nose_bridge', (p[168]+p[6])*.5, .055*width, .12*width),
        ('nose_tip', p[1], .07*width, .06*width),
        ('midface_left', p[[50, 101, 118]].mean(axis=0), .13*width, .12*width),
        ('midface_right', p[[280, 330, 347]].mean(axis=0), .13*width, .12*width),
        ('chin', (p[17]+p[152])*.5, .13*width, .085*width),
    )
    return {'points': p, 'window': (y, x, y1-y, x1-x), 'right': right, 'down': down,
            'width': width, 'radius': radius, 'zones': zones}


def fields(g, shape, skin, excluded, reviewed, protected_boxes, cancelled=None):
    y, x, rh, rw = g['window']; p = g['points']; width = g['width']
    xx = np.arange(x, x+rw, dtype=np.float64)[None, :] + .5
    yy = np.arange(y, y+rh, dtype=np.float64)[:, None] + .5
    inside, distance = _polygon_field(xx, yy, p[list(FACE_OVAL)])
    feather = max(2., .015*width); footprint = math.sqrt(.5)
    permitted = np.where(inside, np.clip((distance-footprint)/feather, 0, 1), 0)
    for ids in (EYE_RING_LEFT, EYE_RING_RIGHT, BROW_LEFT, BROW_RIGHT, LIPS):
        if cancelled is not None and cancelled():
            raise InterruptedError('Facial structure geometry cancelled')
        polygon = p[list(ids)]
        if _crossed(polygon):
            raise ValueError('面部立体眼眉唇保护边界异常')
        occupied, distance = _polygon_field(xx, yy, polygon)
        permitted *= np.where(occupied, 0, np.clip((distance-footprint)/feather, 0, 1))
    # Protect nostril/base projection conservatively; preserve reviewed bridge/tip.
    for index in (98, 327):
        dx, dy = xx-p[index, 0], yy-p[index, 1]
        permitted *= np.clip((np.hypot(dx, dy)-.026*width-footprint)/feather, 0, 1)
    h, w = shape
    for box in boxes(protected_boxes):
        left, top, right, bottom = np.array(box)*[w-1, h-1, w-1, h-1]
        dx = np.maximum(np.maximum(left-xx, xx-right), 0)
        dy = np.maximum(np.maximum(top-yy, yy-bottom), 0)
        permitted *= np.clip((np.hypot(dx, dy)-footprint)/max(2., .02*max(right-left, bottom-top)), 0, 1)
    crop = np.s_[y:y+rh, x:x+rw]
    # Semantic evidence and independent human visibility must BOTH hold. The
    # review is only an additional veto, never replacement segmentation.
    reliable = np.where((skin[crop] >= .75) & (excluded[crop] <= .1),
                        skin[crop]*(1-excluded[crop]), 0)
    support = np.ascontiguousarray(permitted*reliable*reviewed[crop], np.float32)
    zone = np.zeros((rh, rw), np.float64)
    counts = {}
    for name, centre, rx, ry in g['zones']:
        dx, dy = xx-centre[0], yy-centre[1]
        u = (dx*g['right'][0]+dy*g['right'][1])/rx
        v = (dx*g['down'][0]+dy*g['down'][1])/ry
        t = np.clip(1-u*u-v*v, 0, 1)
        local = t*t*(3-2*t)
        np.maximum(zone, local, out=zone)
        counts[name] = int(np.count_nonzero((local > .1) & (support > .1)))
    target = np.ascontiguousarray(support*zone, np.float32)
    if np.count_nonzero(target > .1) < 64 or np.count_nonzero(support > .1) < 128:
        raise ValueError('面部立体缺少足够独立审核的可见皮肤，不补造光影')
    support.setflags(write=False); target.setflags(write=False)
    return support, target, {'zones': counts, 'measured_face_width': width, 'radius': g['radius'],
                            'protected_face_boxes': len(protected_boxes)}
