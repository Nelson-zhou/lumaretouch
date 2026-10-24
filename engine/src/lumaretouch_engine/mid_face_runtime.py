# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-owned measured cheek-to-nose-band length. AUTHORED / UNRUN.

LNX-REF-PC-32466-C-ea67c9d99f follows the positive-lengthens / negative-shortens
direction at https://wiki.pixcakeai.com/guide/9405.html . That page does NOT
specify our solver, boundary, gain or anatomy. The below-all-eye-vertices plane,
.08 gain and conservative evidence gates are original local 2-D policies, not a
clinical middle-third measurement, apple-cheek segmentation or copied solver.

The upper plane is below ALL measured eye polygon vertices. Motion grows to
measured nose proxy 2, then stays constant through every retained below-nose
point, including lips and chin proxy 152, before a below-chin feather. Thus this
map preserves the measured lower-face interval and lip shape, NOT nose shape:
the rising band can change the nose. Proxies are not clinical anatomical truth.

Only Rust computes the inverse. The Python forward-only formula audits all 478
measured targets; it is not an inverse fallback or image sampler. No RGB,
semantic mask, dense field, analysis producer or reconstructed anatomy is kept.
Earlier edits can move points into the feather; there is no global invariance
promise for arbitrary relocated points or commercial photographic parity.
"""
from dataclasses import dataclass

import numpy as np

from . import mid_face_state as S, face_contour_geometry as G
from .face_contour_runtime import require_analysis
from .mid_face_native import canonical_frame, evaluate as native_evaluate
# Reuse measured evidence/validation utilities ONLY, never another control's
# build, field, geometry policy or native evaluation/ABI.
from .lower_face_runtime import _measured_order, _feature_support, _lower_interior_support
from .face_size_runtime import (
    _tiles, _tile_points, _source, _segment_support, _measured_inside, _immutable,
)


MAX_POINTS = 65536
REQUIREMENT_ID = 'LNX-REF-PC-32466-C-ea67c9d99f'
GAIN = .08
CHEEK_PROBES = ((117, 50, 118, -1.), (346, 280, 347, 1.))
LIMITATION = ('2d_existing_texture_only; original_below_eye_cheek_to_nose_policy_not_clinical_middle_third; '
              'measured_point2_point152_proxies_not_clinical_anatomy; not_apple_cheek_segmentation; '
              'rising_band_also_changes_nose_geometry; incomplete_boundary_and_occlusion_evidence; '
              'below_chin_and_lateral_halo_transports_neighboring_neck_background; '
              'prior_edited_points_can_enter_feather_not_global_invariance; '
              'bounded_floating_inverse_not_exact_real_arithmetic; photographic_acceptance_unrun')


def _smooth(value):
    t = np.clip(value, 0., 1.)
    z = np.minimum(t, 1. - t)
    low = z**3 * (10. + z * (-15. + 6. * z))
    return np.where(t <= .5, low, 1. - low)


def _forward_delta(points, parameters):
    """Forward-only retained-target audit; NEVER an inverse-field fallback."""
    local = points - parameters[:2]
    u, t = local @ parameters[2:4], (local @ parameters[4:6]) / parameters[6]
    inner, outer, plateau, tail, amount = parameters[7:]
    lateral = _smooth((outer - np.abs(u)) / (outer - inner))
    lateral[np.abs(u) >= outer] = 0.
    vertical = np.zeros(len(points), np.float64)
    rising = (t > 0.) & (t < 1.)
    flat = (t >= 1.) & (t <= plateau)
    falling = (t > plateau) & (t < plateau + tail)
    vertical[rising] = _smooth(t[rising])
    vertical[flat] = 1.
    vertical[falling] = _smooth((plateau + tail - t[falling]) / tail)
    distance = (((GAIN * parameters[6]) * amount) * lateral) * vertical
    return distance[:, None] * parameters[4:6]


def _measured_band(lm, right, down, width):
    """A conservative measured policy, NOT a clinical facial-thirds solver."""
    nose, lower_height, _, nose_v = _measured_order(lm, right, down, width)
    eye_ids = [index for polygon in G.EYES for index in polygon]
    eye_margin = max(1., .01 * width)
    upper = float(np.max(nose_v[eye_ids])) + eye_margin
    height = -upper
    if not max(16., .08 * width) < height < .50 * width:
        raise ValueError('Mid face has an unresolved measured below-eye-to-nose interval')
    origin = nose - height * down
    u, v = (lm - origin) @ right, (lm - origin) @ down
    epsilon = np.finfo(np.float64).eps * max(1., width, float(np.max(np.abs(lm)))) * 32
    if np.any(v[eye_ids] > -eye_margin + epsilon) or abs(float(v[2]) - height) > epsilon:
        raise ValueError('Mid face upper plane must remain below every measured eye vertex')
    lower = nose_v >= 0.
    padding = max(2., .025 * width)
    plateau = (float(np.max(v[lower])) + padding) / height
    tail = max(.25, .5 * (plateau - 1.))
    if not 1.25 <= plateau <= 8. or not .25 <= tail <= 4.:
        raise ValueError('Mid face measured lower plateau and complete tail exceed native policy bounds')
    inner = float(np.max(np.abs(u[v > 0.]))) + padding
    outer = inner + .25 * width
    if (np.any(np.abs(u[lower]) >= inner) or np.any(v[lower] < height - epsilon)
            or np.any(v[lower] >= plateau * height)):
        raise ValueError('Mid face cannot put every retained lower-face point inside its flat plateau')
    return origin, height, inner, outer, plateau, tail, u, v, lower_height, eye_margin, padding


def _cheek_probe_order(lm, u, v, height, width):
    """Retained surface probes, not semantic apple-cheek or clinical labels.

    Pinned MediaPipe v1.1.1 tessellation contains 118-117-50 and 346-347-280.
    https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py
    The original policy below must be satisfied by this source's measurements;
    no canonical-mesh coordinate is ever inserted as missing anatomy.
    """
    nose_u = u[list(G.NOSE)]
    nose_low = float(np.min(nose_u)) - max(2., .015 * width)
    nose_high = float(np.max(nose_u)) + max(2., .015 * width)
    for upper, lower, neighbor, sign in CHEEK_PROBES:
        ids = [upper, lower, neighbor]
        outside_nose = np.all(u[ids] < nose_low) if sign < 0. else np.all(u[ids] > nose_high)
        if (np.any(v[ids] <= max(1., .05 * height))
                or np.any(v[ids] >= height - max(1., .05 * height))
                or v[lower] - v[upper] <= max(2., .10 * height)
                or not outside_nose):
            raise ValueError('Mid face requires ordered bilateral measured cheek-surface probes outside its nose span')
        distances = np.linalg.norm(lm[[upper, lower]] - lm[neighbor], axis=1)
        if np.any(distances < 1.) or np.any(distances > .35 * width):
            raise ValueError('Mid face cheek-surface neighbor measurements are unresolved')


def _cheek_support(lm, center, origin, right, down, height, width, source, skin, excluded):
    """Independently observe left/right upper/lower cheek-band sectors.

    The actual measured NOSE lateral span plus padding is excluded from cheek
    evidence: nose texture cannot substitute for missing cheeks. These sectors
    are an observation policy, not semantic apple-cheek labels. Known occluders
    veto the whole measured moving oval, including the excluded nose corridor.
    """
    oval = lm[list(G.FACE_OVAL)]
    inset = center + .96 * (oval - center)
    nose_u = (lm[list(G.NOSE)] - origin) @ right
    padding = max(2., .015 * width)
    nose_low, nose_high = float(np.min(nose_u)) - padding, float(np.max(nose_u)) + padding
    if not nose_low < 0. < nose_high or nose_high - nose_low >= .50 * width:
        raise ValueError('Mid face lacks an independently resolved measured cheek/nose span')
    low, high = np.floor(oval.min(0)).astype(int), np.ceil(oval.max(0)).astype(int) + 1
    counts, observed = np.zeros(4, np.int64), np.zeros(4, np.int64)
    totals, totals2 = np.zeros(4, np.float64), np.zeros(4, np.float64)
    probe_ids = [index for upper, lower, neighbor, _ in CHEEK_PROBES for index in (upper, lower, neighbor)]
    probe_radius = max(2., .015 * width)
    probe_counts, probe_observed = np.zeros(6, np.int64), np.zeros(6, np.int64)
    probe_totals, probe_totals2 = np.zeros(6, np.float64), np.zeros(6, np.float64)
    for ys, xs in _tiles(low, high):
        points = _tile_points(ys, xs)
        local = points - origin
        u, v = local @ right, local @ down
        moving_oval = G.polygon_inside(points, oval) & (v > 0.)
        if np.any(moving_oval & (excluded[ys, xs].ravel() >= .15)):
            raise ValueError('Mid face refuses a known occluder inside its measured moving oval')
        eligible = (G.polygon_inside(points, inset) & (v > 0.) & (v < height)
                    & ((u < nose_low) | (u > nose_high)))
        sectors = (u > nose_high).astype(np.int8) + 2 * (v >= .5 * height).astype(np.int8)
        luma = source[ys, xs].reshape(-1, 3) @ np.array([.2126, .7152, .0722])
        usable = eligible & (skin[ys, xs].ravel() >= .45) & (luma > .006) & (luma < .994)
        for sector in range(4):
            selected = sectors == sector
            counts[sector] += np.count_nonzero(eligible & selected)
            sample = luma[usable & selected]
            observed[sector] += len(sample)
            totals[sector] += float(np.sum(sample))
            totals2[sector] += float(sample @ sample)
        for index, landmark in enumerate(probe_ids):
            disk = np.linalg.norm(points - lm[landmark], axis=1) <= probe_radius
            probe_counts[index] += np.count_nonzero(disk)
            sample = luma[disk & usable]
            probe_observed[index] += len(sample)
            probe_totals[index] += float(np.sum(sample))
            probe_totals2[index] += float(sample @ sample)
    divisor = np.maximum(1, observed)
    variances = np.maximum(0., totals2 / divisor - (totals / divisor)**2)
    if (np.any(counts < max(24., width * width * .002))
            or np.any(observed < .85 * counts) or np.any(variances < .0025**2)):
        raise ValueError('Mid face lacks independent skin/RGB evidence in all four cheek-band sectors')
    divisor = np.maximum(1, probe_observed)
    probe_variances = np.maximum(0., probe_totals2 / divisor - (probe_totals / divisor)**2)
    if (np.any(probe_counts < 8) or np.any(probe_observed < .90 * probe_counts)
            or np.any(probe_variances < .0025**2)):
        raise ValueError('Mid face lacks local source skin/RGB evidence at its measured cheek-surface probes')
    return tuple(int(count) for count in observed), int(np.sum(probe_observed)), nose_low, nose_high


@dataclass(frozen=True, init=False)
class MidFaceField:
    """Immutable compact native pullback, with an audited measured lower plateau.

    Guarantees concern this operator's retained source/forward-target geometry,
    not arbitrary earlier relocated points. Passing numerical admission is not
    real-image validation, executed QA or clinical identification.
    """
    shape: tuple
    state: object
    source_landmarks: object
    target_landmarks: object
    _fact_items: tuple

    def __init__(self, parameters, landmarks, target, shape, facts):
        for label, value, required in (('parameters', parameters, (12,)),
                ('source landmarks', landmarks, (478, 2)), ('target landmarks', target, (478, 2))):
            if (type(value) is not np.ndarray or value.dtype != np.float64
                    or value.shape != required or not np.isfinite(value).all()):
                raise ValueError('Mid face needs finite exact-shape float64 ' + label)
        if (type(shape) is not tuple or len(shape) != 2
                or any(type(n) is not int or n < 2 for n in shape)):
            raise ValueError('Mid face needs a two-dimensional source extent')
        if (type(facts) is not dict or any(type(k) is not str or type(v) not in
                (str, int, float, bool, type(None)) for k, v in facts.items())
                or any(type(v) is float and not np.isfinite(v) for v in facts.values())):
            raise ValueError('Mid face facts must contain immutable finite scalar values')
        object.__setattr__(self, 'shape', shape)
        object.__setattr__(self, 'state', _immutable(parameters))
        object.__setattr__(self, 'source_landmarks', _immutable(landmarks))
        object.__setattr__(self, 'target_landmarks', _immutable(target))
        object.__setattr__(self, '_fact_items', tuple(facts.items()))
        expected = _forward_delta(self.source_landmarks, self.state)
        if not np.array_equal(self.source_landmarks + expected, self.target_landmarks):
            raise ValueError('Mid face targets differ from the full requested forward operation')
        actual = self.evaluate(self.target_landmarks)
        motion, error = np.linalg.norm(expected, axis=1), np.linalg.norm(actual - expected, axis=1)
        if np.any(error > motion * 1e-8) or np.any(actual[motion == 0.] != 0.):
            raise ValueError('Mid face native inverse differs from the full requested amount')
        epsilon = np.finfo(np.float64).eps * max(shape) * 32
        if not np.allclose(self.target_landmarks - actual, self.source_landmarks, rtol=0., atol=epsilon):
            raise ValueError('Mid face forward targets do not pull back to their measured source')
        if np.any(np.abs(actual @ self.state[2:4]) > motion * 1e-10):
            raise ValueError('Mid face native inverse changed measured head-axis width')
        local = self.source_landmarks - self.state[:2]
        u, v = local @ self.state[2:4], local @ self.state[4:6]
        upper = v <= 0.
        if np.any(actual[upper] != 0.) or not np.array_equal(self.target_landmarks[upper], self.source_landmarks[upper]):
            raise ValueError('Mid face native inverse changed the upper half-plane')
        eyes = [index for polygon in G.EYES for index in polygon]
        if np.any(v[eyes] >= 0.) or abs(float(v[2]) - self.state[6]) > epsilon:
            raise ValueError('Mid face eye/nose plane does not match its measured band')
        lower = (self.source_landmarks - self.source_landmarks[2]) @ self.state[4:6] >= 0.
        if (not lower[152] or np.any(~lower[list(G.LIPS)])
                or np.any(np.abs(u[lower]) >= self.state[7])
                or np.any(v[lower] < self.state[6] - epsilon)
                or np.any(v[lower] >= self.state[6] * self.state[9])):
            raise ValueError('Mid face retained lower face is not wholly inside its flat plateau')
        plateau_delta = ((GAIN * self.state[6]) * self.state[11]) * self.state[4:6]
        plateau_error = np.linalg.norm(expected[lower] - plateau_delta, axis=1)
        if np.any(plateau_error > np.linalg.norm(plateau_delta) * 1e-10):
            raise ValueError('Mid face did not translate every measured lower-face point equally')
        before = self.source_landmarks[lower] - self.source_landmarks[2]
        after = self.target_landmarks[lower] - self.target_landmarks[2]
        if not np.allclose(after, before, rtol=0., atol=epsilon):
            raise ValueError('Mid face changed the measured lower-face interval or lip shape')
        for upper, lower, _, _ in CHEEK_PROBES:
            before_interval = float((self.source_landmarks[lower] - self.source_landmarks[upper]) @ self.state[4:6])
            after_interval = float((self.target_landmarks[lower] - self.target_landmarks[upper]) @ self.state[4:6])
            if before_interval <= 0. or (after_interval - before_interval) * self.state[11] <= 0.:
                raise ValueError('Mid face requested sign did not change both measured cheek-surface intervals')

    @property
    def parameters(self):
        return self.state

    @property
    def facts(self):
        return {'mid_face': dict(self._fact_items)}

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError('Mid face evaluation needs finite Nx2 pixel coordinates')
        out = np.empty_like(points)
        for start in range(0, len(points), MAX_POINTS):
            q = points[start:start + MAX_POINTS]
            if not np.isfinite(q).all():
                raise ValueError('Mid face evaluation needs finite Nx2 pixel coordinates')
            value = native_evaluate(q, self.state)
            if (type(value) is not np.ndarray or value.dtype != np.float64
                    or value.shape != q.shape or not np.isfinite(value).all()):
                raise ValueError('Mid face native inverse violated its finite float64 output contract')
            out[start:start + len(q)] = value
        return out

    def resident_bytes(self):
        return self.state.nbytes + self.source_landmarks.nbytes + self.target_landmarks.nbytes + 3072


def build(landmarks, recipe, source, excluded, *, backend, analysis, protected_boxes=()):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return None
    if backend != 'mediapipe':
        raise ValueError('Mid face refuses placeholder, template or unverified face geometry')
    _source(source)
    shape = source.shape[:2]
    skin = require_analysis(landmarks, analysis, shape, excluded)
    # Canonical source evidence has float32 hash precision, not caller-added precision.
    lm = G.pixels(np.asarray(analysis['landmarks'], dtype='<f4'), shape)
    measured_right, up, center, width = G.frame(lm)
    right, down = (np.asarray(axis, dtype=np.float64) for axis in canonical_frame(measured_right, -up))
    oval = lm[list(G.FACE_OVAL)]
    _measured_inside(lm, oval, width)
    (origin, height, inner, outer, plateau, tail, u, v,
     lower_height, eye_margin, padding) = _measured_band(lm, right, down, width)
    _cheek_probe_order(lm, u, v, height, width)
    parameters = np.concatenate((origin, right, down,
                                 [height, inner, outer, plateau, tail, recipe['amount']]))
    target = lm + _forward_delta(lm, parameters)
    if np.array_equal(target[2], lm[2]):
        raise ValueError('Mid face nonzero amount is below representable measured geometry precision')
    # Monotonicity and fixed endpoints make the COMPLETE rotated rectangle
    # forward/inverse invariant. Never clip support or attenuate an unsafe request.
    corners = np.array([origin + x * right + y * down for x in (-outer, outer)
                        for y in (0., (plateau + tail) * height)])
    low, high = corners.min(0), corners.max(0)
    h, w = shape
    if np.any(low < 1.) or np.any(high > [w - 2, h - 2]):
        raise ValueError('Mid face complete influence bounding box is clipped by the source frame')
    boxes = G._boxes(protected_boxes, shape)
    if any(np.all(high >= box[:2] - 1.) and np.all(low <= box[2:] + 1.) for box in boxes):
        raise ValueError('Mid face complete influence bounding box touches another retained face')
    boundary_count = boundary_segments = 0
    oval_v = v[list(G.FACE_OVAL)]
    for index, (a, b) in enumerate(zip(oval, np.roll(oval, -1, axis=0))):
        if max(oval_v[index], oval_v[(index + 1) % len(oval)]) <= 0.:
            continue
        reason, count = _segment_support(a, b, center, width, oval, source, skin, excluded)
        if reason:
            raise ValueError('Mid face measured moving-oval support refused: ' + reason)
        boundary_count += count
        boundary_segments += 1
    cheek_counts, cheek_probe_count, nose_low, nose_high = _cheek_support(
        lm, center, origin, right, down, height, width, source, skin, excluded)
    nose_count, lip_count = _feature_support(lm, lm[2], width, source, skin, excluded)
    lower_count = _lower_interior_support(
        lm, center, lm[2], right, down, lower_height, width, source, skin, excluded)
    derivative_bound = 1. - abs(recipe['amount']) * GAIN * 1.875 * max(1., 1. / tail)
    facts = {'control': 'mid_face', 'requirement_id': REQUIREMENT_ID,
             'requested': True, 'applied': True, 'reason': None, 'amount': recipe['amount'],
             'gain': GAIN, 'nose_proxy_index': 2, 'chin_proxy_index': 152,
             'measured_eye_plane_to_nose_interval_px': height, 'eye_margin_px': eye_margin,
             'measured_nose_to_chin_interval_px': lower_height,
             'measured_plateau_padding_px': padding, 'plateau_end_ratio': plateau, 'tail_ratio': tail,
             'boundary_support_px': boundary_count, 'boundary_segments': boundary_segments,
             'cheek_upper_negative_axis_support_px': cheek_counts[0],
             'cheek_upper_positive_axis_support_px': cheek_counts[1],
             'cheek_lower_negative_axis_support_px': cheek_counts[2],
             'cheek_lower_positive_axis_support_px': cheek_counts[3],
             'cheek_surface_probe_support_px': cheek_probe_count,
             'cheek_excluded_nose_axis_min_px': nose_low, 'cheek_excluded_nose_axis_max_px': nose_high,
             'nose_support_px': nose_count, 'lip_support_px': lip_count,
             'lower_interior_support_px': lower_count, 'audited_retained_landmarks': 478,
             'cheek_surface_probe_pairs': '117_to_50;346_to_280',
             'cheek_surface_neighbors': '118;347',
             'audited_lower_plateau_landmarks': int(np.count_nonzero((lm - lm[2]) @ down >= 0.)),
             'minimum_forward_derivative_bound': derivative_bound,
             'method': 'native_bracketed_monotone_mid_face_quintic_plateau_inverse',
             'core_scope': 'retained_measured_lower_face_not_arbitrary_prior_edited_points',
             'evidence': 'moving_oval_strips_four_independent_nose_excluded_cheek_sectors_nose_lips_lower_interior_skin_rgb_occluder_veto',
             'limitation': LIMITATION}
    return MidFaceField(parameters, lm, target, shape, facts)
