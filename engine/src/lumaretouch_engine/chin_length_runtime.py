# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-owned below-lip chin length, separate from lower-third and small_chin.

AUTHORED / UNRUN. LNX-REF-PC-32466-C-44a42baef4 follows left-shortens /
right-lengthens at https://wiki.pixcakeai.com/guide/9405.html . Positive amount
lengthens the measured below-lip-to-tip interval; negative shortens it. The .08
gain and admission thresholds are original bounded 2-D policies, not commercial
calibration, clinical chin measurements or photographic acceptance.

All 40 measured lip vertices are above the fixed plane. The plane's lateral
coordinate is actual tip152; H ends at that same measured tip, not an invented
chin center. The complete true lower-oval arc is 150-149-176-148-152-377-400-
378-379 in the pinned MediaPipe v1.1.1 FACE_LANDMARKS_FACE_OVAL topology:
https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py
Those vertices are measured geometry, never clinical anatomy or visibility.

The NEW thin bridge reuses the existing original lower_face Rust primitive.
Only Rust computes the inverse. Python's forward expression audits all 478
retained targets; it never samples an image or substitutes a second inverse.
No RGB, masks, analysis producer, model, or synthetic anatomy is retained here.
"""
from dataclasses import dataclass

import numpy as np

from . import chin_length_state as S, face_contour_geometry as G
from .chin_length_native import canonical_frame, evaluate as native_evaluate
from .face_contour_runtime import require_analysis
# Read-only source/measurement helpers, never another operation's build.
from .lower_face_runtime import _measured_order, _inside_or_boundary
from .face_size_runtime import _tiles, _tile_points, _source, _measured_inside, _immutable


MAX_POINTS = 65536
REQUIREMENT_ID = 'LNX-REF-PC-32466-C-44a42baef4'
GAIN = .08
TAIL = .5
LOWER_ARC = (150, 149, 176, 148, 152, 377, 400, 378, 379)
INNER_LIPS = (78, 191, 80, 81, 82, 13, 312, 311, 310, 415,
              308, 324, 318, 402, 317, 14, 87, 178, 88, 95)
LIP_VERTICES = tuple(sorted(set((*G.LIPS, *INNER_LIPS))))
LIMITATION = ('2d_existing_texture_only; measured_lower_oval_not_clinical_chin_anatomy; '
              'incomplete_boundary_and_occlusion_evidence; '
              'below_chin_and_lateral_halo_transports_neighboring_neck_background; '
              'full_support_rectangle_guard_is_conservative; '
              'prior_edited_points_can_enter_feather_not_global_lip_invariance; '
              'canonical_frame_roundoff_not_bitwise_real_axis_identity; '
              'head_axis_width_invariance_with_explicit_f64_tolerance; '
              'bounded_floating_inverse_not_exact_real_arithmetic; photographic_acceptance_unrun')


def _smooth(value):
    t = np.clip(value, 0., 1.)
    z = np.minimum(t, 1. - t)
    low = z**3 * (10. + z * (-15. + 6. * z))
    return np.where(t <= .5, low, 1. - low)


def _forward_delta(points, parameters):
    """Forward-only retained-target audit, never an inverse/image fallback."""
    local = points - parameters[:2]
    u = local[:, 0] * parameters[2] + local[:, 1] * parameters[3]
    t = (local[:, 0] * parameters[4] + local[:, 1] * parameters[5]) / parameters[6]
    inner, outer, tail, amount = parameters[7:]
    lateral = _smooth((outer - np.abs(u)) / (outer - inner))
    lateral[np.abs(u) >= outer] = 0.
    vertical = np.zeros(len(points), np.float64)
    rising, falling = (t > 0.) & (t <= 1.), (t > 1.) & (t < 1. + tail)
    vertical[rising] = _smooth(t[rising])
    vertical[falling] = _smooth((1. + tail - t[falling]) / tail)
    distance = (((GAIN * parameters[6]) * amount) * lateral) * vertical
    return distance[:, None] * parameters[4:6]


def _measured_chin(lm, right, down, width):
    """Require real ordered lips/tip/lower oval, with no repair or extrapolation."""
    _measured_order(lm, right, down, width)
    lips = lm[list(G.LIPS)]
    if not np.all(_inside_or_boundary(lm[list(INNER_LIPS)], lips, max(.25, .001 * width))):
        raise ValueError('Chin length inner lip vertices leave the measured outer lip polygon')
    tip = lm[152]
    tip_v = (lm - tip) @ down
    lip_margin = max(1., .01 * width)
    height = -(float(np.max(tip_v[list(LIP_VERTICES)])) + lip_margin)
    if not max(16., .08 * width) < height < .50 * width:
        raise ValueError('Chin length has an unresolved measured below-lip-to-tip interval')
    origin = tip - height * down
    u, v = (lm - origin) @ right, (lm - origin) @ down
    epsilon = np.finfo(np.float64).eps * max(1., width, float(np.max(np.abs(lm)))) * 32
    if (abs(float(u[152])) > epsilon or abs(float(v[152]) - height) > epsilon
            or np.any(v[list(LIP_VERTICES)] > -lip_margin + epsilon)):
        raise ValueError('Chin length plane does not protect every measured lip or actual tip axis')
    arc_u, arc_v = u[list(LOWER_ARC)], v[list(LOWER_ARC)]
    step = max(.2, .001 * width)
    if (np.any(np.diff(arc_u) <= max(.5, .003 * width))
            or np.any(np.diff(arc_v[:5]) <= step)
            or np.any(np.diff(arc_v[4:]) >= -step)
            or np.any(arc_v < .10 * height) or np.any(arc_v > height + epsilon)
            or not u[148] < -max(1., .005 * width) < max(1., .005 * width) < u[377]
            or not .25 * width < float(np.ptp(arc_u)) < .90 * width):
        raise ValueError('Chin length requires the complete ordered measured lower-oval arc')
    padding = max(2., .025 * width)
    inner = float(np.max(np.abs(u[v > 0.]))) + padding
    # Same finite measured-width halo policy as the reused lower_face primitive.
    # The height and origin here remain this separate below-lip operation's.
    outer = inner + .25 * width
    if not np.isfinite(outer) or not 0. < inner < outer or np.any(np.abs(arc_u) >= inner):
        raise ValueError('Chin length cannot enclose its measured moving oval in the lateral core')
    return origin, height, inner, outer, u, v, lip_margin, padding


def _moving(points, origin, right, down, height, outer):
    local = points - origin
    u, v = local @ right, local @ down
    # Unlike horizontal chin taper, the centerline including tip152 DOES move.
    return (v > 0.) & (v < (1. + TAIL) * height) & (np.abs(u) < outer)


def _chin_segment_support(a, b, center, width, oval, source, skin, excluded,
                          origin, right, down, height, outer):
    """Require actual inset skin/RGB on each moving measured oval segment."""
    edge = b - a
    length = float(np.linalg.norm(edge))
    if length < .5:
        raise ValueError('Chin length has a degenerate measured moving-oval segment')
    inward = np.array([-edge[1], edge[0]]) / length
    if inward @ (center - (a + b) * .5) < 0.:
        inward = -inward
    near, far = max(.8, width * .012), max(3., width * .07)
    poly = np.array([a + near * inward, b + near * inward,
                     b + far * inward, a + far * inward])
    low, high = np.floor(poly.min(0) - 1).astype(int), np.ceil(poly.max(0) + 2).astype(int)
    h, w = source.shape[:2]
    if np.any(low < 1) or np.any(high > [w - 1, h - 1]):
        raise ValueError('Chin length clipped measured moving-oval skin support')
    count = inside_count = visible_count = observed = 0
    total = total2 = 0.
    for ys, xs in _tiles(low, high):
        points = _tile_points(ys, xs)
        selected = G.polygon_inside(points, poly) & _moving(points, origin, right, down, height, outer)
        inside = selected & G.polygon_inside(points, oval)
        visible = inside & (skin[ys, xs].ravel() >= .45) & (excluded[ys, xs].ravel() < .15)
        luma = source[ys, xs].reshape(-1, 3) @ np.array([.2126, .7152, .0722])
        sample = luma[visible & (luma > .006) & (luma < .994)]
        count += int(np.count_nonzero(selected))
        inside_count += int(np.count_nonzero(inside))
        visible_count += int(np.count_nonzero(visible))
        observed += len(sample)
        total += float(np.sum(sample)); total2 += float(sample @ sample)
    variance = max(0., total2 / max(1, observed) - (total / max(1, observed))**2)
    if (inside_count < max(12., .85 * count) or visible_count < max(12., .88 * inside_count)
            or observed < .90 * visible_count or variance < .0025**2):
        raise ValueError('Chin length lacks actual moving-oval strip skin/RGB support')
    return observed


def _chin_support(lm, center, origin, right, down, height, width, source, skin, excluded, outer):
    """Observe all four below-lip sectors and all nine actual lower-arc probes.

    Probes are real pixel neighborhoods clipped to the measured oval, never
    generated anatomy or halo evidence. A whole-moving-oval occluder veto also
    covers the centerline and the actual tip. No cheek/upper-oval proxy counts
    as lower chin. Each sector and each probe needs its own RGB variation.
    """
    oval = lm[list(G.FACE_OVAL)]
    inset = center + .96 * (oval - center)
    low, high = np.floor(oval.min(0)).astype(int), np.ceil(oval.max(0)).astype(int) + 1
    counts, observed = np.zeros(4, np.int64), np.zeros(4, np.int64)
    totals, totals2 = np.zeros(4, np.float64), np.zeros(4, np.float64)
    radius = max(3., .025 * width)
    probe_counts, probe_observed = np.zeros(9, np.int64), np.zeros(9, np.int64)
    probe_totals, probe_totals2 = np.zeros(9, np.float64), np.zeros(9, np.float64)
    for ys, xs in _tiles(low, high):
        points = _tile_points(ys, xs)
        local = points - origin
        u, v = local @ right, local @ down
        moving = G.polygon_inside(points, oval) & _moving(points, origin, right, down, height, outer)
        if np.any(moving & (excluded[ys, xs].ravel() >= .15)):
            raise ValueError('Chin length refuses a known occluder inside its measured moving oval')
        eligible = G.polygon_inside(points, inset) & moving & (v < height)
        sectors = (u >= 0.).astype(np.int8) + 2 * (v >= .5 * height).astype(np.int8)
        luma = source[ys, xs].reshape(-1, 3) @ np.array([.2126, .7152, .0722])
        usable = (skin[ys, xs].ravel() >= .45) & (luma > .006) & (luma < .994)
        for sector in range(4):
            selected = eligible & (sectors == sector)
            counts[sector] += np.count_nonzero(selected)
            sample = luma[selected & usable]
            observed[sector] += len(sample)
            totals[sector] += float(np.sum(sample)); totals2[sector] += float(sample @ sample)
        for index, landmark in enumerate(LOWER_ARC):
            selected = moving & (np.linalg.norm(points - lm[landmark], axis=1) <= radius)
            probe_counts[index] += np.count_nonzero(selected)
            sample = luma[selected & usable]
            probe_observed[index] += len(sample)
            probe_totals[index] += float(np.sum(sample)); probe_totals2[index] += float(sample @ sample)
    divisor = np.maximum(1, observed)
    variance = np.maximum(0., totals2 / divisor - (totals / divisor)**2)
    if (np.any(counts < max(16., width * width * .001))
            or np.any(observed < .85 * counts) or np.any(variance < .0025**2)):
        raise ValueError('Chin length lacks independent skin/RGB evidence in all lower-chin sectors')
    divisor = np.maximum(1, probe_observed)
    variance = np.maximum(0., probe_totals2 / divisor - (probe_totals / divisor)**2)
    if (np.any(probe_counts < 6) or np.any(probe_observed < .90 * probe_counts)
            or np.any(variance < .0025**2)):
        raise ValueError('Chin length lacks local source skin/RGB beside actual measured lower-arc vertices')
    return tuple(int(value) for value in observed), tuple(int(value) for value in probe_observed)


def _lip_support(lm, down, width, source, excluded):
    """Actual lower-lip RGB is required even though measured lips stay fixed."""
    lips = lm[list(G.LIPS)]
    low, high = np.floor(lips.min(0)).astype(int), np.ceil(lips.max(0)).astype(int) + 1
    h, w = source.shape[:2]
    if np.any(low < 1) or np.any(high > [w - 1, h - 1]):
        raise ValueError('Chin length clipped measured lower-lip evidence')
    middle = (lm[13] + lm[14]) * .5
    count = observed = 0
    total = total2 = 0.
    for ys, xs in _tiles(low, high):
        points = _tile_points(ys, xs)
        inside = G.polygon_inside(points, lips)
        if np.any(inside & (excluded[ys, xs].ravel() >= .15)):
            raise ValueError('Chin length refuses a known occluder at its measured lips')
        selected = inside & ((points - middle) @ down >= 0.)
        luma = source[ys, xs].reshape(-1, 3) @ np.array([.2126, .7152, .0722])
        sample = luma[selected & (luma > .006) & (luma < .994)]
        count += int(np.count_nonzero(selected)); observed += len(sample)
        total += float(np.sum(sample)); total2 += float(sample @ sample)
    variance = max(0., total2 / max(1, observed) - (total / max(1, observed))**2)
    if count < max(12., width * width * .0002) or observed < .90 * count or variance < .0025**2:
        raise ValueError('Chin length lacks real measured lower-lip RGB evidence')
    return observed


@dataclass(frozen=True, init=False)
class ChinLengthField:
    """Immutable compact native pullback with audited genuine measured targets."""
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
                raise ValueError('Chin length needs finite exact-shape float64 ' + label)
        if (type(shape) is not tuple or len(shape) != 2
                or any(type(n) is not int or n < 2 for n in shape)):
            raise ValueError('Chin length needs a two-dimensional source extent')
        if (parameters[6] <= 0. or not 0. < parameters[7] < parameters[8]
                or parameters[9] != TAIL or not -1. <= parameters[10] <= 1. or parameters[10] == 0.):
            raise ValueError('Chin length requires its measured positive interval, halo, tail and active signed amount')
        # Validate orthonormality, without a second host normalization/repair.
        # Re-normalizing an already canonical f64 axis need not be bit-idempotent.
        canonical_frame(parameters[2:4], parameters[4:6])
        if (type(facts) is not dict or any(type(k) is not str or type(v) not in
                (str, int, float, bool, type(None)) for k, v in facts.items())
                or any(type(v) is float and not np.isfinite(v) for v in facts.values())):
            raise ValueError('Chin length facts must contain immutable finite scalar values')
        object.__setattr__(self, 'shape', shape)
        object.__setattr__(self, 'state', _immutable(parameters))
        object.__setattr__(self, 'source_landmarks', _immutable(landmarks))
        object.__setattr__(self, 'target_landmarks', _immutable(target))
        object.__setattr__(self, '_fact_items', tuple(facts.items()))
        expected = _forward_delta(self.source_landmarks, self.state)
        if not np.array_equal(self.source_landmarks + expected, self.target_landmarks):
            raise ValueError('Chin length targets differ from the full requested forward operation')
        actual = self.evaluate(self.target_landmarks)
        motion = np.linalg.norm(expected, axis=1)
        error = np.linalg.norm(actual - expected, axis=1)
        if np.any(error > motion * 1e-8) or np.any(actual[motion == 0.] != 0.):
            raise ValueError('Chin length native inverse differs from the full requested amount')
        epsilon = np.finfo(np.float64).eps * max(shape) * 32
        if not np.allclose(self.target_landmarks - actual, self.source_landmarks, rtol=0., atol=epsilon):
            raise ValueError('Chin length targets do not pull back to their actual measured source')
        local = self.source_landmarks - self.state[:2]
        u, v = local @ self.state[2:4], local @ self.state[4:6]
        target_u = (self.target_landmarks - self.state[:2]) @ self.state[2:4]
        target_v = (self.target_landmarks - self.state[:2]) @ self.state[4:6]
        if (np.any(np.abs(actual @ self.state[2:4]) > motion * 1e-10)
                or np.any(np.abs(target_u - u) > epsilon)):
            raise ValueError('Chin length changed measured head-axis width')
        if (np.any(v[list(LIP_VERTICES)] >= 0.)
                or not np.array_equal(self.target_landmarks[list(LIP_VERTICES)], self.source_landmarks[list(LIP_VERTICES)])
                or np.any(actual[list(LIP_VERTICES)] != 0.)):
            raise ValueError('Chin length changed measured lips or failed to protect their plane')
        upper = v <= 0.
        if np.any(actual[upper] != 0.) or not np.array_equal(self.target_landmarks[upper], self.source_landmarks[upper]):
            raise ValueError('Chin length changed the protected upper half-plane')
        rows = list(LOWER_ARC)
        if (abs(float(u[152])) > epsilon or abs(float(v[152]) - self.state[6]) > epsilon
                or np.any(v[rows] <= 0.) or np.any(v[rows] > self.state[6] + epsilon)
                or np.any(np.abs(u[rows]) >= self.state[7])):
            raise ValueError('Chin length cannot audit actual tip152 and the complete measured lower arc')
        change = target_v[rows] - v[rows]
        if ((self.state[10] > 0. and np.any(change <= 0.))
                or (self.state[10] < 0. and np.any(change >= 0.))):
            raise ValueError('Chin length requested sign did not move every actual lower-arc vertex')
        tip_delta = (GAIN * self.state[6]) * self.state[10]
        if (not np.allclose(expected[152], tip_delta * self.state[4:6], rtol=1e-12, atol=0.)
                or abs(float(target_v[152]) - (self.state[6] + tip_delta)) > epsilon):
            raise ValueError('Chin length changed its actual-tip interval by the wrong amount')

    @property
    def parameters(self):
        return self.state

    @property
    def facts(self):
        return {'chin_length': dict(self._fact_items)}

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError('Chin length evaluation needs finite Nx2 pixel coordinates')
        out = np.empty_like(points)
        for start in range(0, len(points), MAX_POINTS):
            q = points[start:start + MAX_POINTS]
            if not np.isfinite(q).all():
                raise ValueError('Chin length evaluation needs finite Nx2 pixel coordinates')
            value = native_evaluate(q, self.state)
            if (type(value) is not np.ndarray or value.dtype != np.float64
                    or value.shape != q.shape or not np.isfinite(value).all()):
                raise ValueError('Chin length native inverse violated its finite float64 output contract')
            out[start:start + len(q)] = value
        return out

    def resident_bytes(self):
        return self.state.nbytes + self.source_landmarks.nbytes + self.target_landmarks.nbytes + 3072


def build(landmarks, recipe, source, excluded, *, backend, analysis, protected_boxes=()):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return None
    if backend != 'mediapipe':
        raise ValueError('Chin length refuses placeholder, template or unverified face geometry')
    _source(source)
    shape = source.shape[:2]
    skin = require_analysis(landmarks, analysis, shape, excluded)
    lm = G.pixels(np.asarray(analysis['landmarks'], dtype='<f4'), shape)
    measured_right, up, center, width = G.frame(lm)
    right, down = (np.asarray(axis, dtype=np.float64) for axis in canonical_frame(measured_right, -up))
    oval = lm[list(G.FACE_OVAL)]
    _measured_inside(lm, oval, width)
    origin, height, inner, outer, u, v, margin, padding = _measured_chin(lm, right, down, width)
    parameters = np.concatenate((origin, right, down, [height, inner, outer, TAIL, recipe['amount']]))
    target = lm + _forward_delta(lm, parameters)
    if np.any(np.all(target[list(LOWER_ARC)] == lm[list(LOWER_ARC)], axis=1)):
        raise ValueError('Chin length nonzero amount is below representable measured geometry precision')
    # Monotone native vertical map has fixed support edges: the COMPLETE rotated
    # support rectangle is invariant. Never clip it or lower requested strength.
    corners = np.array([origin + x * right + y * down for x in (-outer, outer)
                        for y in (0., (1. + TAIL) * height)])
    low, high = corners.min(0), corners.max(0)
    h, w = shape
    if np.any(low < 1.) or np.any(high > [w - 2, h - 2]):
        raise ValueError('Chin length complete influence bounding box is clipped by the source frame')
    boxes = G._boxes(protected_boxes, shape)
    if any(np.all(high >= box[:2] - 1.) and np.all(low <= box[2:] + 1.) for box in boxes):
        raise ValueError('Chin length complete influence bounding box touches another retained face')
    boundary_count = boundary_segments = 0
    oval_v = v[list(G.FACE_OVAL)]
    for index, (a, b) in enumerate(zip(oval, np.roll(oval, -1, axis=0))):
        following = (index + 1) % len(oval)
        if max(oval_v[index], oval_v[following]) <= 0.:
            continue
        boundary_count += _chin_segment_support(a, b, center, width, oval, source, skin, excluded,
                                                origin, right, down, height, outer)
        boundary_segments += 1
    sectors, probes = _chin_support(lm, center, origin, right, down, height, width, source, skin, excluded, outer)
    lip_count = _lip_support(lm, down, width, source, excluded)
    amount = recipe['amount']
    epsilon = np.finfo(np.float64).eps * max(shape) * 32
    facts = {'control': 'chin_length', 'requirement_id': REQUIREMENT_ID,
             'requested': True, 'applied': True, 'reason': None, 'amount': amount,
             'gain': GAIN, 'tail_ratio': TAIL, 'actual_tip_index': 152,
             'measured_lip_plane_to_tip_interval_px': height,
             'target_lip_plane_to_tip_interval_px': height + (GAIN * height) * amount,
             'lip_margin_px': margin, 'measured_lateral_padding_px': padding,
             'lateral_halo_width_ratio': .25,
             'boundary_support_px': boundary_count, 'boundary_segments': boundary_segments,
             'upper_subject_right_skin_rgb_px': sectors[0], 'upper_subject_left_skin_rgb_px': sectors[1],
             'lower_subject_right_skin_rgb_px': sectors[2], 'lower_subject_left_skin_rgb_px': sectors[3],
             'lower_arc_probe_support_px': sum(probes), 'lower_arc_probe_count': len(probes),
             'lower_lip_rgb_px': lip_count, 'protected_lip_vertices': len(LIP_VERTICES),
             'audited_retained_landmarks': 478, 'audited_lower_arc': '-'.join(map(str, LOWER_ARC)),
             'minimum_forward_vertical_slope_bound': 1. - GAIN * 1.875 / TAIL * abs(amount),
             'maximum_forward_vertical_slope_bound': 1. + GAIN * 1.875 / TAIL * abs(amount),
             'head_axis_audit_tolerance_px': float(epsilon),
             'method': 'existing_lower_face_native_bracketed_monotone_vertical_inverse',
             'core_scope': 'retained_measured_below_lip_chin_not_arbitrary_prior_edited_points',
             'evidence': 'all_moving_oval_strips_veto_four_chin_sectors_nine_actual_arc_probes_lower_lip_rgb',
             'limitation': LIMITATION}
    return ChinLengthField(parameters, lm, target, shape, facts)
