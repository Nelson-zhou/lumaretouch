# SPDX-License-Identifier: GPL-3.0-or-later
"""Measured, source-local face frame and fail-closed visible-skin support.

The frame describes only decoration placement, not inferred anatomy. Real eyes,
brows, lips, nose base and face boundary are protected. Reviewed nose bridge is
allowed; the blush operation's bilateral cheek masks are intentionally not used.
Review is a necessary human visibility veto, not proof of complete segmentation.
"""
import numpy as np
from .face_scope import _polygon_field, FACE_OVAL, BROW_LEFT, BROW_RIGHT
from .lip_makeup_geometry import OUTER as LIPS, _crossed

EYES = (
    (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246),
    (263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466),
)
MAX_PIXELS = 4_000_000


def mask(value, shape, label):
    if (type(value) is not np.ndarray or value.shape != tuple(shape)
            or value.dtype != np.float32 or not np.isfinite(value).all()
            or np.any((value < 0) | (value > 1))):
        raise ValueError('面部装饰缺少有效的当前源图' + label)
    return value


def _visible_support(geometry, skin, excluded, reviewed):
    """Semantic confidence is thresholded; human opacity is never thresholded."""
    evidence = np.where((skin >= .7) & (excluded < .1), skin * (1 - excluded), 0)
    return np.ascontiguousarray(geometry * evidence * reviewed, dtype=np.float32)


def fields(landmarks, shape, skin, excluded, *, backend, reviewed):
    h, w = shape
    if min(h, w) < 4 or h * w > MAX_PIXELS:
        raise ValueError('面部装饰原始尺寸窗口超预算；未降采样')
    lm = np.asarray(landmarks, np.float32)
    if backend != 'mediapipe' or lm.shape != (478, 2) or not np.isfinite(lm).all():
        raise ValueError('面部装饰需要真实 478 点人物分析')
    mask(skin, shape, '皮肤证据'); mask(excluded, shape, '遮挡排除证据')
    mask(reviewed, shape, '独立装饰可见皮肤审核')
    eye_widths = [float(np.linalg.norm(lm[a] - lm[b])) for a, b in ((33, 133), (263, 362))]
    halves = [float(np.linalg.norm(lm[a] - lm[1])) for a in (234, 454)]
    if min(eye_widths) < 12 or min(halves) < 32:
        raise ValueError('人物分辨率不足，面部装饰暂不应用')
    if min(eye_widths) < .65 * max(eye_widths) or min(halves) < .65 * max(halves):
        raise ValueError('侧脸过强，面部装饰暂不应用')
    oval = lm[list(FACE_OVAL)]
    if (_crossed(oval) or np.any(oval < 2) or np.any(oval[:, 0] > w - 2)
            or np.any(oval[:, 1] > h - 2)):
        raise ValueError('脸部边界被裁切或异常，面部装饰暂不应用')
    axis_u = (lm[454] - lm[234]) * .5
    scale = float(np.linalg.norm(axis_u))
    if scale < 40 or axis_u[0] <= 0:
        raise ValueError('脸部横轴异常，面部装饰暂不应用')
    right = axis_u / scale
    down = np.array([-right[1], right[0]], np.float32)
    eye_mid = (lm[33] + lm[263]) * .5
    face_down = lm[152] - eye_mid
    height = float(np.dot(face_down, down))
    if height < .8 * scale or height > 2.6 * scale or abs(float(np.dot(face_down, right))) > .4 * scale:
        raise ValueError('脸部俯仰或纵轴不可靠，面部装饰暂不应用')
    if not .15 < float(np.dot(lm[1] - eye_mid, down)) / height < .65:
        raise ValueError('鼻部与眼颌位置不可靠，面部装饰暂不应用')
    frame = np.ascontiguousarray(np.stack((lm[1], axis_u, down * scale)), dtype=np.float32)
    # Broadcast coordinate vectors avoid two full-size coordinate-grid copies.
    xs = np.arange(w, dtype=np.float64)[None, :] + .5
    ys = np.arange(h, dtype=np.float64)[:, None] + .5
    inside, edge = _polygon_field(xs, ys, oval)
    pixel_radius = np.sqrt(.5)
    clearance = max(1.5, min(eye_widths) * .10)
    support = np.where(inside, np.clip((edge - pixel_radius) / clearance, 0, 1), 0)
    for ids in (*EYES, BROW_LEFT, BROW_RIGHT, LIPS):
        polygon = lm[list(ids)]
        if _crossed(polygon):
            raise ValueError('眼眉唇边界异常，面部装饰未应用')
        occupied, distance = _polygon_field(xs, ys, polygon)
        support *= np.where(occupied, 0, np.clip((distance - pixel_radius) / clearance, 0, 1))
    # Protect the measured nasal base (including nostrils), not the whole bridge.
    # These MediaPipe mesh vertices are spatial evidence; the connecting capsule
    # is an intentionally conservative exclusion, not a claimed nostril contour.
    nasal_clearance = max(2.0, float(np.linalg.norm(lm[98] - lm[327])) * .20)
    for a, b in ((98, 97), (97, 2), (2, 326), (326, 327)):
        start, end = lm[a], lm[b]
        direction = end - start
        length2 = float(np.dot(direction, direction))
        if length2 < .25:
            raise ValueError('鼻部边界退化，面部装饰未应用')
        t = np.clip(((xs - start[0]) * direction[0] + (ys - start[1]) * direction[1]) / length2, 0, 1)
        distance = np.hypot(xs - start[0] - t * direction[0], ys - start[1] - t * direction[1])
        support *= np.clip((distance - pixel_radius - nasal_clearance) / clearance, 0, 1)
    # Semantics/review never expand geometry. Foreign faces and known occluders
    # arrive in excluded from the verified people pipeline, not this frame.
    # Human brush coverage is not semantic confidence. Preserve its feather and
    # partial eraser opacity after thresholding the independent semantic plane.
    support = _visible_support(support, skin, excluded, reviewed)
    return frame, support, {
        'reviewed_support_pixels': int(np.count_nonzero(support)),
        'face_frame': 'measured-nose-origin-cheek-width-affine',
        'visibility_method': 'decoration-review-intersected-with-actual-skin-and-exclusions',
        'limitation': 'known-occluders-and-human-review-not-complete-instance-segmentation',
    }
