# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-owned lower-third length, distinct from legacy mouth-pinned small_chin.

AUTHORED / UNRUN. LNX-REF-PC-32466-C-1ae8316994 follows the signed direction
at https://wiki.pixcakeai.com/guide/9405.html : positive lengthens, negative
shortens. The .08 gain, admission thresholds and compact feather are original
bounded 2-D policies, not commercial calibration or photographic acceptance.

The pinned MediaPipe v1.1.1 topology connects 94 -> 2, 97 -> 2 -> 326 and
377 -> 152 -> 148. These are measured nose/chin PROXIES, not clinically located
subnasale/menton or proof of visibility. H is their head-axis projected interval.
https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py

All admitted below-nose interior, including lips, participates. Width and the
upper half-plane stay fixed for this operator. Only Rust evaluates the inverse;
the forward-only formula below audits retained measured targets. The existing
people owner remains the only image sampler. No dense field, RGB, semantic mask,
analysis producer, downloaded model or reconstructed anatomy is retained here.
"""
from dataclasses import dataclass

import numpy as np

from . import lower_face_state as S, face_contour_geometry as G
from .face_contour_runtime import require_analysis
from .lower_face_native import canonical_frame, evaluate as native_evaluate
# Common source-validation/evidence utilities ONLY. Importing these helpers does
# not call FaceSizeField/build/evaluate or require/load the face-size native ABI.
from .face_size_runtime import (
    _tiles, _tile_points, _source, _segment_support, _measured_inside, _immutable,
)


MAX_POINTS = 65536
REQUIREMENT_ID = 'LNX-REF-PC-32466-C-1ae8316994'
GAIN = .08
TAIL = .5
LIMITATION = ('2d_existing_texture_only; measured_point2_point152_proxies_not_clinical_anatomy; '
              'incomplete_boundary_and_occlusion_evidence; '
              'below_chin_and_lateral_halo_transports_neighboring_neck_background; '
              'prior_edited_points_can_enter_feather_not_identity_pinned; '
              'bounded_floating_inverse_not_exact_real_arithmetic; photographic_acceptance_unrun')


def _smooth(value):
    t = np.clip(value, 0., 1.)
    # Symmetric evaluation avoids cancellation at the quintic's zero edge.
    z = np.minimum(t, 1. - t)
    low = z**3 * (10. + z * (-15. + 6. * z))
    return np.where(t <= .5, low, 1. - low)


def _forward_delta(points, parameters):
    """Forward-only retained-target audit; NEVER an inverse deformation fallback."""
    local = points - parameters[:2]
    u, t = local @ parameters[2:4], (local @ parameters[4:6]) / parameters[6]
    inner, outer, tail, amount = parameters[7:]
    lateral = _smooth((outer - np.abs(u)) / (outer - inner))
    lateral[np.abs(u) >= outer] = 0.
    vertical = np.zeros(len(points), np.float64)
    rising, falling = (t > 0.) & (t <= 1.), (t > 1.) & (t < 1. + tail)
    vertical[rising] = _smooth(t[rising])
    vertical[falling] = _smooth((1. + tail - t[falling]) / tail)
    distance = (((GAIN * parameters[6]) * amount) * lateral) * vertical
    return distance[:, None] * parameters[4:6]


def _inside_or_boundary(points, poly, tolerance):
    inside = G.polygon_inside(points, poly)
    for a, b in zip(poly, np.roll(poly, -1, axis=0)):
        edge = b - a
        t = np.clip(((points - a) @ edge) / float(edge @ edge), 0., 1.)
        inside |= np.linalg.norm(points - a - t[:, None] * edge, axis=1) <= tolerance
    return inside


def _measured_order(lm, right, down, width):
    """Conservative measured 2-D ordering, not anthropometric identification."""
    origin = lm[2]
    u, v = (lm - origin) @ right, (lm - origin) @ down
    height = float(v[152])
    if not max(32., .22 * width) < height < .95 * width:
        raise ValueError('Lower face has an unresolved measured nose-to-chin interval')
    lips = lm[list(G.LIPS)]
    lip_u, lip_v = u[list(G.LIPS)], v[list(G.LIPS)]
    if (v[94] >= -max(.5, .0025 * width)
            or not u[97] < -.005 * width < .005 * width < u[326]
            or max(abs(v[97]), abs(v[326])) > .15 * height
            or float(np.mean(v[[468, 473]])) >= -.04 * width
            or abs(float(u[152])) > .20 * width
            or abs(float(np.mean(lip_u))) > .18 * width
            or np.min(lip_v) <= max(2., .06 * height)
            or np.max(lip_v) >= height - max(3., .10 * height)
            or not .15 * width < float(np.ptp(lip_u)) < .65 * width
            or not .15 * height < float(np.mean(lip_v)) < .75 * height
            or not np.all(_inside_or_boundary(lm[[13, 14]], lips, max(.25, .001 * width)))
            # Closed lips can coincide. Do not invent an opening; only reject
            # a materially inverted measured inner-lip order.
            or v[13] > v[14] + max(.5, .005 * height)
            or not u[148] < 0. < u[377]
            or np.any(v[[148, 377]] < .80 * height)
            or np.any(v[[148, 377]] > 1.03 * height)):
        raise ValueError('Lower face requires conservative measured nose/lip/chin ordering')
    oval_v = v[list(G.FACE_OVAL)]
    if np.count_nonzero(oval_v > 0) < 8 or np.max(oval_v) > height + max(.75, .015 * height):
        raise ValueError('Lower face requires actual ordered lower-oval support')
    return origin, height, u, v


def _feature_support(lm, origin, width, source, skin, excluded):
    """Require actual local RGB at nose proxy and measured lip polygon.

    Lip pixels need not be classified as skin, but never bypass RGB or known
    occlusion checks. The small nose disk is a photometric probe, not anatomy.
    Neither landmarks nor synthetic interpolated anatomy are evidence here.
    """
    oval, lips = lm[list(G.FACE_OVAL)], lm[list(G.LIPS)]
    radius = max(2., .018 * width)
    counts = []
    for name, low, high in (
            ('nose', np.floor(origin - radius - 1).astype(int), np.ceil(origin + radius + 2).astype(int)),
            ('lips', np.floor(lips.min(0)).astype(int), np.ceil(lips.max(0)).astype(int) + 1)):
        h, w = source.shape[:2]
        if np.any(low < 1) or np.any(high > [w - 1, h - 1]):
            raise ValueError('Lower face clipped measured ' + name + ' evidence')
        count = usable_count = 0
        total = total2 = 0.
        for ys, xs in _tiles(low, high):
            points = _tile_points(ys, xs)
            selected = (np.linalg.norm(points - origin, axis=1) <= radius if name == 'nose'
                        else G.polygon_inside(points, lips))
            if np.any(selected & ~G.polygon_inside(points, oval)):
                raise ValueError('Lower face measured feature evidence extends outside its oval')
            if np.any(selected & (excluded[ys, xs].ravel() >= .15)):
                raise ValueError('Lower face has a known occluder at measured ' + name)
            luma = source[ys, xs].reshape(-1, 3) @ np.array([.2126, .7152, .0722])
            usable = selected & (luma > .006) & (luma < .994)
            if name == 'nose':
                usable &= skin[ys, xs].ravel() >= .45
            count += int(np.count_nonzero(selected))
            sample = luma[usable]
            usable_count += len(sample)
            total += float(np.sum(sample)); total2 += float(sample @ sample)
        variance = max(0., total2 / max(1, usable_count) - (total / max(1, usable_count))**2)
        if count < 12 or usable_count < .90 * count or variance < .0025**2:
            raise ValueError('Lower face lacks real source ' + name + ' skin/RGB evidence')
        counts.append(usable_count)
    return tuple(counts)


def _lower_interior_support(lm, center, origin, right, down, height, width, source, skin, excluded):
    """Observe all four lower-face sectors; lip skin exemption is not a veto exemption."""
    inset = center + .96 * (lm[list(G.FACE_OVAL)] - center)
    low, high = np.floor(inset.min(0)).astype(int), np.ceil(inset.max(0)).astype(int) + 1
    counts, observed = np.zeros(4, np.int64), np.zeros(4, np.int64)
    count = 0
    total = total2 = 0.
    for ys, xs in _tiles(low, high):
        points = _tile_points(ys, xs)
        local = points - origin
        u, v = local @ right, local @ down
        interior = G.polygon_inside(points, inset) & (v > 0) & (v <= height)
        if np.any(interior & (excluded[ys, xs].ravel() >= .15)):
            raise ValueError('Lower face refuses a known occluder inside its measured lower interior')
        eligible = interior & ~G.polygon_inside(points, lm[list(G.LIPS)])
        sectors = (u >= 0).astype(np.int8) + 2 * (v >= .5 * height).astype(np.int8)
        luma = source[ys, xs].reshape(-1, 3) @ np.array([.2126, .7152, .0722])
        usable = eligible & (skin[ys, xs].ravel() >= .45) & (luma > .006) & (luma < .994)
        for sector in range(4):
            counts[sector] += np.count_nonzero(eligible & (sectors == sector))
            observed[sector] += np.count_nonzero(usable & (sectors == sector))
        sample = luma[usable]
        count += len(sample)
        total += float(np.sum(sample)); total2 += float(sample @ sample)
    variance = max(0., total2 / max(1, count) - (total / max(1, count))**2)
    if (np.any(counts < max(24., width * width * .002))
            or np.any(observed < .85 * counts) or variance < .0025**2):
        raise ValueError('Lower face lacks source face-skin/RGB evidence across its lower interior')
    return count


@dataclass(frozen=True, init=False)
class LowerFaceField:
    """Immutable compact native pullback, with no pinned mouth or width change.

    This operator's guarantee covers retained measured source/forward-target
    geometry. Earlier edits can move points into its lateral/below-chin feather.
    A successful audit is floating-point numerical admission, not executed QA.
    """
    shape: tuple
    state: object
    source_landmarks: object
    target_landmarks: object
    _fact_items: tuple

    def __init__(self, parameters, landmarks, target, shape, facts):
        for label, value, required in (('parameters', parameters, (11,)),
                ('source landmarks', landmarks, (478, 2)), ('target landmarks', target, (478, 2))):
            if (type(value) is not np.ndarray or value.dtype != np.float64
                    or value.shape != required or not np.isfinite(value).all()):
                raise ValueError('Lower face needs finite exact-shape float64 ' + label)
        if (type(shape) is not tuple or len(shape) != 2
                or any(type(n) is not int or n < 2 for n in shape)):
            raise ValueError('Lower face needs a two-dimensional source extent')
        if (type(facts) is not dict or any(type(k) is not str or type(v) not in
                (str, int, float, bool, type(None)) for k, v in facts.items())
                or any(type(v) is float and not np.isfinite(v) for v in facts.values())):
            raise ValueError('Lower face facts must contain immutable finite scalar values')
        object.__setattr__(self, 'shape', shape)
        object.__setattr__(self, 'state', _immutable(parameters))
        object.__setattr__(self, 'source_landmarks', _immutable(landmarks))
        object.__setattr__(self, 'target_landmarks', _immutable(target))
        object.__setattr__(self, '_fact_items', tuple(facts.items()))
        expected = _forward_delta(self.source_landmarks, self.state)
        if not np.array_equal(self.source_landmarks + expected, self.target_landmarks):
            raise ValueError('Lower face targets differ from the full requested forward operation')
        actual = self.evaluate(self.target_landmarks)
        motion = np.linalg.norm(expected, axis=1)
        error = np.linalg.norm(actual - expected, axis=1)
        if np.any(error > motion * 1e-8) or np.any(actual[motion == 0] != 0):
            raise ValueError('Lower face native inverse differs from the full requested amount')
        epsilon = np.finfo(np.float64).eps * max(shape) * 32
        if not np.allclose(self.target_landmarks - actual, self.source_landmarks, rtol=0., atol=epsilon):
            raise ValueError('Lower face forward targets do not pull back to their measured source')
        if np.any(np.abs(actual @ self.state[2:4]) > motion * 1e-10):
            raise ValueError('Lower face native inverse changed measured head-axis width')
        upper = (self.source_landmarks - self.state[:2]) @ self.state[4:6] <= 0
        if np.any(actual[upper] != 0) or not np.array_equal(self.target_landmarks[upper], self.source_landmarks[upper]):
            raise ValueError('Lower face native inverse changed the upper-face half-plane')

    @property
    def parameters(self):
        return self.state

    @property
    def facts(self):
        return {'lower_face': dict(self._fact_items)}

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError('Lower face evaluation needs finite Nx2 pixel coordinates')
        out = np.empty_like(points)
        for start in range(0, len(points), MAX_POINTS):
            q = points[start:start + MAX_POINTS]
            if not np.isfinite(q).all():
                raise ValueError('Lower face evaluation needs finite Nx2 pixel coordinates')
            value = native_evaluate(q, self.state)
            if (type(value) is not np.ndarray or value.dtype != np.float64
                    or value.shape != q.shape or not np.isfinite(value).all()):
                raise ValueError('Lower face native inverse violated its finite float64 output contract')
            out[start:start + len(q)] = value
        return out

    def resident_bytes(self):
        return self.state.nbytes + self.source_landmarks.nbytes + self.target_landmarks.nbytes + 2048


def build(landmarks, recipe, source, excluded, *, backend, analysis, protected_boxes=()):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return None
    if backend != 'mediapipe':
        raise ValueError('Lower face refuses placeholder, template or unverified face geometry')
    _source(source)
    shape = source.shape[:2]
    skin = require_analysis(landmarks, analysis, shape, excluded)
    # Canonical hash precision is float32; extra caller precision is not evidence.
    lm = G.pixels(np.asarray(analysis['landmarks'], dtype='<f4'), shape)
    measured_right, up, center, width = G.frame(lm)
    right, down = (np.asarray(axis, dtype=np.float64) for axis in canonical_frame(measured_right, -up))
    oval = lm[list(G.FACE_OVAL)]
    _measured_inside(lm, oval, width)
    origin, height, u, v = _measured_order(lm, right, down, width)
    # Every measured lower-oval point, lip and lower-interior point lies in the
    # lateral flat core. No generic template widens it or supplies missing points.
    measured_lower = v > 0
    inner_x = float(np.max(np.abs(u[measured_lower]))) + max(2., .025 * width)
    outer_x = inner_x + .25 * width
    parameters = np.concatenate((origin, right, down, [height, inner_x, outer_x, TAIL, recipe['amount']]))
    target = lm + _forward_delta(lm, parameters)
    if np.array_equal(target[152], lm[152]):
        raise ValueError('Lower face nonzero amount is below representable measured geometry precision')
    # This entire rectangle is both forward- and inverse-invariant: monotonicity
    # and fixed vertical endpoints keep every admitted source within its support.
    corners = np.array([origin + x * right + y * down for x in (-outer_x, outer_x)
                        for y in (0., (1. + TAIL) * height)])
    low, high = corners.min(0), corners.max(0)
    h, w = shape
    if np.any(low < 1) or np.any(high > [w - 2, h - 2]):
        raise ValueError('Lower face complete influence bounding box is clipped by the source frame')
    boxes = G._boxes(protected_boxes, shape)
    if any(np.all(high >= box[:2] - 1) and np.all(low <= box[2:] + 1) for box in boxes):
        raise ValueError('Lower face complete influence bounding box touches another retained face')
    boundary_count = boundary_segments = 0
    oval_v = v[list(G.FACE_OVAL)]
    for i, (a, b) in enumerate(zip(oval, np.roll(oval, -1, axis=0))):
        if max(oval_v[i], oval_v[(i + 1) % len(oval)]) <= 0:
            continue
        reason, count = _segment_support(a, b, center, width, oval, source, skin, excluded)
        if reason:
            raise ValueError('Lower face measured lower-oval support refused: ' + reason)
        boundary_count += count
        boundary_segments += 1
    nose_count, lip_count = _feature_support(lm, origin, width, source, skin, excluded)
    interior_count = _lower_interior_support(lm, center, origin, right, down, height, width, source, skin, excluded)
    derivative_bound = 1. - abs(recipe['amount']) * GAIN * 1.875 * max(1., 1. / TAIL)
    facts = {'control': 'lower_face', 'requirement_id': REQUIREMENT_ID,
             'requested': True, 'applied': True, 'reason': None, 'amount': recipe['amount'],
             'gain': GAIN, 'nose_proxy_index': 2, 'chin_proxy_index': 152,
             'measured_head_axis_interval_px': height, 'tail_ratio': TAIL,
             'boundary_support_px': boundary_count, 'boundary_segments': boundary_segments,
             'nose_support_px': nose_count, 'lip_support_px': lip_count,
             'interior_support_px': interior_count, 'audited_retained_landmarks': 478,
             'minimum_forward_derivative_bound': derivative_bound,
             'method': 'native_bracketed_monotone_lower_third_quintic_inverse',
             'core_scope': 'retained_measured_lower_face_not_arbitrary_prior_edited_points',
             'evidence': 'measured_lower_oval_strips_nose_lips_four_lower_sectors_source_skin_rgb_known_occluder_veto',
             'limitation': LIMITATION}
    return LowerFaceField(parameters, lm, target, shape, facts)
