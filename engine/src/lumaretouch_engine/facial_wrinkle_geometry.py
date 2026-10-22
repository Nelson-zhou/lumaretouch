# SPDX-License-Identifier: AGPL-3.0-only
"""Original eight-region FaceMesh geometry using pinned RapidRetouch primitives.

Not an upstream eight-region implementation or an occlusion classifier. Rules
use the actually selected 478-point face and conservative semantic skin weights.
Each side can be refused independently; no fallback whole-face smoothing.
"""
import numpy as np
from .third_party.rapidretouch import under_eye as E
from .ops.enhance import LIP_CHAIN_UPPER, LIP_CHAIN_LOWER
from .facial_wrinkle_state import KEYS


def _poly(shape, points):
    # Anatomical patches are convex subsets; mouth/eye boundaries retain their
    # own ordered contours below, rather than filling a hull across an opening.
    pts = np.ascontiguousarray(points, dtype=np.float32)
    return E._poly_mask(shape, E.cv2.convexHull(pts).reshape(-1, 2))


def _grow(mask, radius):
    return E.grow_mask(mask, 2 * max(1, round(radius)) + 1)


def _stroke(shape, points, width):
    out = np.zeros(shape, np.uint8)
    E.cv2.polylines(out, [np.round(np.asarray(points) * 16).astype(np.int32)], False,
                   1, max(1, round(width * 2)), lineType=E.cv2.LINE_AA, shift=4)
    return out.astype(np.float32)


def geometry(landmarks_px, shape, skin_weight):
    """Return masks, independent per-region/side reasons, and face-relative scale.

    Input skin_weight is already max(2*p_skin-1,0), NOT a person matte or raw
    probability. Zero semantic support and anatomical exclusion stay exact zero.
    """
    if E.cv2 is None:
        raise RuntimeError('面部祛纹需要 OpenCV；不会退回整脸模糊')
    lm = np.asarray(landmarks_px, np.float32)
    if lm.shape != (478, 2) or not np.isfinite(lm).all():
        raise ValueError('面部祛纹需要选中人物真实的 478 点')
    h, w = shape
    if min(h, w) < 4 or h * w > 32_000_000:
        raise ValueError('面部祛纹 ROI 尺寸超出预算；未降采样替代全尺寸处理')
    zeros = lambda: np.zeros(shape, np.float32)
    if skin_weight is None:
        return ({key: zeros() for key in KEYS}, {key: {'geom_px': 0, 'gated_px': 0,
                 'reason': 'skin_semantics_unavailable', 'sides': {}} for key in KEYS}, 0.)
    skin = np.asarray(skin_weight, np.float32)
    if skin.shape != shape or not np.isfinite(skin).all() or np.any((skin < 0) | (skin > 1)):
        raise ValueError('面部祛纹皮肤支持场无效或没有对齐源图')
    geos = {side: E._eye_geometry(lm, spec) for side, spec in E.EYES.items()}
    scale = max(g['eye_w'] for g in geos.values())
    down = E._face_down(lm)
    across = lm[263] - lm[33]
    across /= max(float(np.linalg.norm(across)), 1e-6)
    face = E._inner_feather(E._poly_mask(shape, lm[E.FACE_OVAL]), max(.5, .1 * scale))
    protect = zeros()
    for geo in geos.values():
        protect = np.maximum(protect, _grow(E._poly_mask(shape, geo['contour']), .10 * scale))
        protect = np.maximum(protect, _grow(E._poly_mask(shape, geo['brow']), .12 * scale))
    lip = E._poly_mask(shape, lm[list(LIP_CHAIN_UPPER) + list(LIP_CHAIN_LOWER[-2:0:-1])])
    protect = np.maximum(protect, _grow(lip, .08 * scale))
    # Both nostril openings + alar rims. Never relight these structural shadows.
    for indices in ([98, 97, 2, 164, 0, 37, 39, 40, 92, 165],
                    [327, 326, 2, 164, 0, 267, 269, 270, 322, 391]):
        protect = np.maximum(protect, _grow(_poly(shape, lm[indices]), .04 * scale))
    safe = np.ascontiguousarray(face * skin * (1 - protect), dtype=np.float32)
    # A semantic boundary/occluder needs an inward clearance, not a blurred halo.
    safe *= E.cv2.erode((skin > .05).astype(np.uint8),
                       E.cv2.getStructuringElement(E.cv2.MORPH_ELLIPSE,
                           (2 * max(1, round(.025 * scale)) + 1,) * 2))
    rows = {key: [] for key in KEYS}
    def add(name, mask, side='center', reason=None):
        rows['wrinkle_' + name].append((mask, side, reason))
    def reason(side):
        width = geos[side]['eye_w']
        if width < E.MIN_EYE_PX: return 'insufficient_resolution'
        if width < .45 * scale: return 'foreshortened_or_inadequate_pose'
        return None
    both_reason = ('inadequate_pose_for_central_region' if min(g['eye_w'] for g in geos.values()) < .45 * scale
                   else 'insufficient_resolution' if scale < E.MIN_EYE_PX else None)
    # Forehead is bounded by the actual face-oval top and brow rows. Sideways
    # hairstyles remain excluded by semantic support, never by color guessing.
    add('forehead', _poly(shape, lm[[10, 109, 67, 103, 54, 70, 63, 105, 66, 107,
                                    9, 336, 296, 334, 293, 300, 284, 332, 297, 338]]), reason=both_reason)
    add('glabellar', _poly(shape, lm[[107, 9, 336, 285, 168, 55]]), reason=both_reason)
    add('nose', _poly(shape, lm[[168, 193, 122, 196, 3, 51, 5, 281, 248, 419, 351, 417]]), reason=both_reason)
    for side, geo in geos.items():
        why = reason(side)
        eye = np.maximum(E._poly_mask(shape, geo['under_eye_lines']), E._poly_mask(shape, geo['crows_feet']))
        # Include upper/periorbital skin, still behind the hard brow/lash guard.
        eye = np.maximum(eye, _grow(E._poly_mask(shape, geo['contour']), .25 * geo['eye_w']))
        add('eye_area', eye, side, why)
        is_left = side == 'left'  # subject's left, NOT screen-left
        ala, corner = lm[327 if is_left else 98], lm[291 if is_left else 61]
        outward = across if is_left else -across
        cheek = [280, 330, 425, 411, 352, 345, 346, 347, 348, 329] if is_left else [50, 101, 205, 187, 123, 116, 117, 118, 119, 100]
        add('cheek', _poly(shape, lm[cheek]), side, why)
        # An anatomical corridor, not a claim that every dark pixel is a fold.
        # The Hessian ridge detector decides which lines within it get lifted.
        middle = .55 * ala + .45 * corner + .10 * scale * outward
        naso = _stroke(shape, [ala + .06 * scale * outward, middle,
                              corner + .12 * scale * outward + .12 * scale * down], .19 * scale)
        add('nasolabial_' + side, naso, side, why)
        end = corner + .65 * scale * down + .10 * scale * outward
        add('marionette', _stroke(shape, [corner + .08 * scale * outward, end], .20 * scale), side, why)
    add('mouth_surround', _grow(lip, .35 * scale), reason=both_reason)
    masks, facts = {}, {}
    for key, parts in rows.items():
        union, geom_total, sides = zeros(), 0, {}
        for hard, side, why in parts:
            geom_count = int(np.count_nonzero(hard))
            geom_total += geom_count
            candidate = E._inner_feather(hard, max(.5, .06 * scale)) * safe
            count = int(np.count_nonzero(candidate > .01))
            if not why and (geom_count < 16 or count < 12): why = 'no_eligible_skin_or_occluded'
            if not why and count < geom_count * .12: why = 'insufficient_visible_skin_support'
            if why: candidate[:] = 0
            sides[side] = {'geom_px': geom_count, 'gated_px': 0 if why else count, 'reason': why}
            union = np.maximum(union, candidate)
        masks[key] = np.ascontiguousarray(union, dtype=np.float32)
        count = int(np.count_nonzero(union > .01))
        reasons = [p['reason'] for p in sides.values() if p['reason']]
        facts[key] = {'geom_px': geom_total, 'gated_px': count, 'reason': None if count else
                      (reasons[0] if reasons else 'no_eligible_skin_or_occluded'), 'sides': sides,
                      'partial': bool(count and reasons)}
    return masks, facts, float(scale)
