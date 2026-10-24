# SPDX-License-Identifier: GPL-3.0-or-later
"""Measured, source-owned temple/cheekbone/jaw contour controls.

The oval is the factual MediaPipe v1.1.1 FACE_LANDMARKS_FACE_OVAL topology:
https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py
Regional roles, gains and admission thresholds are our conservative 2-D policy,
not MediaPipe anatomy labels or PixCake implementation details. Slider directions
follow https://wiki.pixcakeai.com/guide/9405.html . No upstream code is copied.

Landmarks can veto geometry, never prove visibility. Admission additionally needs
authenticated face-skin observations, actual RGB and known-occluder exclusion.
This is not complete boundary/occlusion segmentation, nor a 3-D reconstruction.
"""
from __future__ import annotations

import numpy as np

from . import face_contour_state as S
from .face_contour_native import controls as native_controls
from .face_scope import FACE_OVAL, BROW_LEFT, BROW_RIGHT


# Subject left lies along iris 468 -> 473, independent of screen rotation.
# NEVER use ops.deform.FACE_OVAL_LEFT/RIGHT: those are a different legacy policy.
CHAINS = {
    'right': (21, 162, 127, 234, 93, 132, 58, 172, 136, 150, 149),
    'left': (251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378),
}
REGIONS = {
    'temple': (0, 1, 2, 3),
    'cheekbone': (2, 3, 4, 5, 6),
    'jaw': (5, 6, 7, 8, 9, 10),
}
# Independent original smooth tapers; endpoints and the rest of the oval pin.
ROLE_WEIGHTS = (
    (0., 0., 0.), (1., 0., 0.), (.65, .15, 0.),
    (0., 1., 0.), (0., .7, 0.), (0., .2, 0.),
    (0., 0., .3), (0., 0., 1.), (0., 0., .8),
    (0., 0., .3), (0., 0., 0.),
)
EYES = (
    (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246),
    (263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466),
)
LIPS = (61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146)
NOSE = (168, 6, 197, 195, 5, 4, 1, 19, 94, 2, 98, 97, 327, 326)
IDENTITY_POLYGONS = (*EYES, BROW_LEFT, BROW_RIGHT, LIPS)
ANCHORS = tuple(sorted(set((*NOSE, *range(468, 478),
                            *(i for ids in IDENTITY_POLYGONS for i in ids)))))
BORDER = ((0., 0.), (1., 0.), (0., 1.), (1., 1.),
          (.5, 0.), (.5, 1.), (0., .5), (1., .5))
LIMITATION = ('2d_existing_texture_only; inner_skin_evidence_not_complete_boundary_or_occlusion_segmentation; '
              'compact_halo_transports_adjacent_background_not_perfect_background_isolation')


class FaceContourRefusal(ValueError):
    """An unsupported requested side makes the entire transaction unavailable."""
    def __init__(self, facts, message='Face contour request refused'):
        self.facts = {
            key: {**fact, 'applied': False,
                  'reason': fact['reason'] or ('atomic_request_refused' if fact['requested'] else None)}
            for key, fact in facts.items()
        }
        refused = {key: value['reason'] for key, value in self.facts.items() if value['requested']}
        super().__init__(f'{message}; no requested side was applied: {refused}')


def pixels(landmarks, shape):
    """NEW operator's integer pixel centers: normalized 0/1 maps to 0/(N-1)."""
    if len(shape) != 2 or any(type(n) not in (int, np.int64, np.int32) or n < 2 for n in shape):
        raise ValueError('Face contour needs a nonempty two-dimensional source frame')
    lm = np.asarray(landmarks, dtype=np.float64)
    if lm.shape != (478, 3) or not np.isfinite(lm).all() or np.any((lm[:, :2] < 0) | (lm[:, :2] > 1)):
        raise ValueError('Face contour needs measured normalized 478x3 landmarks')
    h, w = shape
    return np.ascontiguousarray(lm[:, :2] * [w - 1, h - 1])


def polygon_inside(points, poly):
    points = np.asarray(points, dtype=np.float64)
    inside = np.zeros(len(points), dtype=bool)
    x, y = points.T
    for a, b in zip(poly, np.roll(poly, -1, axis=0)):
        if abs(b[1] - a[1]) < 1e-12:
            continue
        inside ^= ((a[1] > y) != (b[1] > y)) & (x < a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]))
    return inside


def _area(poly):
    nxt = np.roll(poly, -1, axis=0)
    return .5 * abs(float(np.sum(poly[:, 0] * nxt[:, 1] - nxt[:, 0] * poly[:, 1])))


def _simple_polygon(poly):
    """Reject degenerate/crossing measured boundaries, not just small area."""
    n = len(poly)
    def cross(a, b):
        return float(a[0] * b[1] - a[1] * b[0])
    for i, (a, b) in enumerate(zip(poly, np.roll(poly, -1, axis=0))):
        if np.linalg.norm(b - a) < .10:
            return False
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            c, d = poly[j], poly[(j + 1) % n]
            denominator = cross(b - a, d - c)
            if abs(denominator) < 1e-10:
                # Collinear overlap is not a valid simple boundary either.
                if abs(cross(c - a, b - a)) < 1e-8:
                    axis = int(np.argmax(np.abs(b - a)))
                    if max(min(a[axis], b[axis]), min(c[axis], d[axis])) <= min(max(a[axis], b[axis]), max(c[axis], d[axis])):
                        return False
                continue
            t = cross(c - a, d - c) / denominator
            u = cross(c - a, b - a) / denominator
            if 0 <= t <= 1 and 0 <= u <= 1:
                return False
    return True


def frame(lm):
    right = lm[473] - lm[468]
    iris_span = float(np.linalg.norm(right))
    if iris_span < 24:
        raise ValueError('insufficient_resolution')
    right = right / iris_span
    up = np.array([right[1], -right[0]])
    if (lm[10] - lm[152]) @ up < 0:
        up = -up
    center = (lm[234] + lm[454]) * .5
    width = float((lm[454] - lm[234]) @ right)
    height = float((lm[10] - lm[152]) @ up)
    if width < 64 or height < 72:
        raise ValueError('insufficient_resolution')
    if not .65 < height / width < 2.1 or not .22 < iris_span / width < .72:
        raise ValueError('degenerate_contour_geometry')
    eye_widths = [float(np.linalg.norm(lm[a] - lm[b])) for a, b in ((33, 133), (263, 362))]
    half_widths = [float((lm[1] - lm[234]) @ right), float((lm[454] - lm[1]) @ right)]
    if (min(eye_widths) < 10 or min(eye_widths) < .72 * max(eye_widths)
            or min(half_widths) < .29 * width or max(half_widths) > .71 * width):
        raise ValueError('sideface_or_foreshortened')
    oval = lm[list(FACE_OVAL)]
    if _area(oval) < width * height * .40 or not _simple_polygon(oval):
        raise ValueError('degenerate_contour_geometry')
    if any(_area(lm[list(ids)]) < max(2., width * width * .00008)
           or not _simple_polygon(lm[list(ids)]) for ids in IDENTITY_POLYGONS):
        raise ValueError('degenerate_identity_feature_geometry')
    for side, ids in CHAINS.items():
        chain = lm[list(ids)]
        sign = 1. if side == 'left' else -1.
        if (np.any(np.diff(chain @ up) > height * .025)
                or np.any(np.linalg.norm(np.diff(chain, axis=0), axis=1) < max(.6, width * .003))
                or np.any((chain - center) @ (sign * right) < width * .08)):
            raise ValueError('folded_or_degenerate_contour_chain')
    return right, up, center, width


def _support_segment(a, b, center, width, oval, source, skin, excluded):
    """Inspect an actual inset strip of the selected source oval, not its halo."""
    edge = b - a
    length = float(np.linalg.norm(edge))
    if length < .5:
        return 'degenerate_contour_segment', 0
    inward = np.array([-edge[1], edge[0]]) / length
    if inward @ (center - (a + b) * .5) < 0:
        inward = -inward
    near, far = max(.8, width * .012), max(3., width * .07)
    poly = np.array([a + near * inward, b + near * inward,
                     b + far * inward, a + far * inward])
    h, w = source.shape[:2]
    low = np.floor(poly.min(0) - 1).astype(int)
    high = np.ceil(poly.max(0) + 2).astype(int)
    if np.any(low < 1) or high[0] > w - 1 or high[1] > h - 1:
        return 'clipped_inner_skin_support', 0
    x0, y0 = low; x1, y1 = high
    yy, xx = np.mgrid[y0:y1, x0:x1]
    points = np.stack((xx.ravel(), yy.ravel()), axis=1)
    strip = polygon_inside(points, poly)
    inside = strip & polygon_inside(points, oval)
    if np.count_nonzero(inside) < max(12, .85 * np.count_nonzero(strip)):
        return 'insufficient_inner_oval_strip', int(np.count_nonzero(inside))
    skin_patch = skin[y0:y1, x0:x1].ravel()
    veto = excluded[y0:y1, x0:x1].ravel()
    visible = inside & (skin_patch >= .45) & (veto < .15)
    count = int(np.count_nonzero(visible))
    if count < max(12, .88 * np.count_nonzero(inside)):
        return 'occluded_or_missing_face_skin_support', count
    # No skin-colour template: require usable local source signal only. Smooth,
    # clipped or low-contrast skin can conservatively fail this heuristic.
    luma = source[y0:y1, x0:x1].reshape(-1, 3) @ np.array([.2126, .7152, .0722])
    usable = visible & (luma > .006) & (luma < .994)
    if np.count_nonzero(usable) < .90 * count or float(np.std(luma[usable])) < .0025:
        return 'no_reliable_local_rgb_evidence', int(np.count_nonzero(usable))
    return None, int(np.count_nonzero(usable))


def evidence(lm, recipe, source, skin, excluded):
    r = S.check(recipe)
    common = None
    try:
        right, up, center, width = frame(lm)
    except ValueError as error:
        common = str(error)
        right = up = center = np.zeros(2, np.float64); width = 0.
    if excluded is None or skin is None:
        common = 'authenticated_visibility_support_unavailable'
    facts = {}
    oval = lm[list(FACE_OVAL)]
    for key in S.KEYS:
        for side in S.SIDES:
            reason, count = common, 0
            if reason is None:
                chain = lm[[CHAINS[side][i] for i in REGIONS[key]]]
                for a, b in zip(chain[:-1], chain[1:]):
                    failure, amount = _support_segment(a, b, center, width, oval, source, skin, excluded)
                    count += amount
                    reason = reason or failure
            requested = r[key][side] != 0
            facts[f'{key}/{side}'] = {
                'control': key, 'side': side, 'requested': requested, 'applied': requested and reason is None,
                'reason': reason, 'support_px': count,
                'method': 'source_face_skin_inner_oval_strip_plus_rgb_and_known_occluder_veto',
                'limitation': LIMITATION,
            }
    return facts, right, up, center, width


def _boxes(value, shape):
    boxes = np.asarray(value, dtype=np.float64)
    if boxes.size == 0:
        if boxes.shape not in ((0,), (0, 4)):
            raise ValueError('Empty protected faces must still have a valid box collection shape')
        return np.empty((0, 4), np.float64)
    if (boxes.ndim != 2 or boxes.shape[1] != 4 or len(boxes) > 4096 or not np.isfinite(boxes).all()
            or np.any((boxes < 0) | (boxes > 1)) or np.any(boxes[:, :2] >= boxes[:, 2:])):
        raise ValueError('Protected faces require bounded normalized source boxes')
    h, w = shape
    return boxes * [w - 1, h - 1, w - 1, h - 1]


def window_overlaps_box(window, box):
    center, _, radius = window
    nearest = np.clip(center, box[:2], box[2:])
    # Include the bilinear pixel footprint, not only exact landmark positions.
    return float(np.linalg.norm(center - nearest)) <= radius + np.sqrt(.5)


def build_controls(landmarks, shape, recipe, source, excluded, *, backend, skin, protected_boxes=()):
    r = S.check(recipe)
    if backend != 'mediapipe':
        raise ValueError('Face contour refuses template or placeholder face geometry')
    lm = pixels(landmarks, shape)
    if (type(source) is not np.ndarray or source.dtype not in (np.float32, np.float64)
            or source.shape != (*shape, 3) or not np.isfinite(source).all()
            or np.any((source < 0) | (source > 1))):
        raise ValueError('Face contour needs actual same-frame source float RGB in [0,1]')
    for name, value in (('face_skin', skin), ('excluded', excluded)):
        if value is not None and (type(value) is not np.ndarray or value.shape != tuple(shape)
                or not np.isfinite(value).all() or np.any((value < 0) | (value > 1))):
            raise ValueError(f'Face contour {name} evidence differs from the source frame')
    boxes = _boxes(protected_boxes, shape)
    facts, right, up, center, width = evidence(lm, r, source, skin, excluded)
    if any(f['requested'] and not f['applied'] for f in facts.values()):
        raise FaceContourRefusal(facts)
    points = lm[list(FACE_OVAL)]
    roles = np.zeros((len(points), 3), np.float64)
    sides = np.where((points - center) @ right >= 0, 1., -1.).astype(np.float64)
    for side, ids in CHAINS.items():
        for index, weights in zip(ids, ROLE_WEIGHTS):
            row = FACE_OVAL.index(index)
            roles[row] = weights
            sides[row] = 1. if side == 'left' else -1.
    values = np.array([r[key][side] for key in S.KEYS for side in S.SIDES], np.float64)
    measured_frame = np.concatenate((right, up, center, [width])).astype(np.float64)
    delta = native_controls(points, roles, sides, measured_frame, values)
    if (type(delta) is not np.ndarray or delta.shape != points.shape or delta.dtype != np.float64
            or not np.isfinite(delta).all() or np.any(np.linalg.norm(delta, axis=1) > width * .08 + 1e-10)):
        raise ValueError('Face contour native controls violated their bounded finite displacement contract')
    # Each region has an exclusive unit-weight peak. Check requested direction
    # and amplitude there independently of TPS/protection, including tiny values.
    # This verifies the Rust contract; it is not a Python replacement kernel.
    peaks = {'temple': 1, 'cheekbone': 3, 'jaw': 7}
    for key in S.KEYS:
        for side in S.SIDES:
            row = FACE_OVAL.index(CHAINS[side][peaks[key]])
            sign = (1. if side == 'left' else -1.) * (-1. if key == 'cheekbone' else 1.)
            expected = right * (sign * width * .035 * r[key][side])
            if not np.allclose(delta[row], expected, rtol=1e-9, atol=0.):
                raise ValueError(f'Face contour native request mismatch at {key}/{side}')
    target = points + delta
    h, w = shape
    if np.any(target < 1) or np.any(target[:, 0] >= w - 2) or np.any(target[:, 1] >= h - 2):
        raise ValueError('Face contour target is clipped by the source boundary')
    windows = []
    for key_index, key in enumerate(S.KEYS):
        for side in S.SIDES:
            if r[key][side] == 0:
                continue
            indices = [FACE_OVAL.index(i) for i in CHAINS[side] if roles[FACE_OVAL.index(i), key_index] > 0]
            both = np.concatenate((points[indices], target[indices]))
            c = both.mean(0)
            flat = float(np.max(np.linalg.norm(both - c, axis=1))) + width * .04
            window = (c, flat, flat + width * .18)
            reason = None
            if np.any(c - window[2] < 1) or c[0] + window[2] > w - 2 or c[1] + window[2] > h - 2:
                reason = 'clipped_complete_influence_window'
            if any(window_overlaps_box(window, box) for box in boxes):
                reason = 'foreign_or_unresolved_face_in_complete_influence_window'
            if reason:
                facts[f'{key}/{side}']['reason'] = reason
                raise FaceContourRefusal(facts)
            windows.append(window)
    # P is the DESTINATION, D the forward motion. Thus P-D is exactly the
    # original measured control, not a forward field incorrectly used as inverse.
    anchors = lm[list(ANCHORS)]
    P = np.concatenate((target, anchors, np.asarray(BORDER) * [w - 1, h - 1]))
    D = np.concatenate((delta, np.zeros((len(anchors) + len(BORDER), 2))))
    requested_P, requested_D = P.copy(), D.copy()
    from .ops.deform import dedupe_controls
    tolerance = max(.002, width * 1e-5)
    for i in range(len(P)):
        close = np.linalg.norm(P[i + 1:] - P[i], axis=1) < tolerance
        if np.any(D[i + 1:][close] != D[i]):
            raise ValueError('Face contour controls conflict with stable identity anchors')
    P, D, merged = dedupe_controls(P, D, tol=tolerance)
    pinned_segments = []
    for i, j in zip(range(len(points)), np.roll(np.arange(len(points)), -1)):
        if np.all(delta[i] == 0) and np.all(delta[j] == 0):
            pinned_segments.append(np.array([points[i], points[j]]))
    return P, D, {
        'controls': facts, 'merged': merged, 'windows': windows, 'landmarks': lm,
        'width': width, 'pinned_segments': np.asarray(pinned_segments, np.float64).reshape(-1, 2, 2),
        'requested_P': requested_P, 'requested_D': requested_D,
        'source_contour': points.copy(), 'target_contour': target,
    }
