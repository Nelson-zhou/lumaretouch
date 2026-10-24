# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-owned horizontal chin taper, distinct from chin/lower-face length.

AUTHORED / UNRUN. LNX-REF-PC-32466-C-ed7837df9a follows the rounder-left /
sharper-right slider direction at https://wiki.pixcakeai.com/guide/9405.html .
Positive contracts and negative expands each measured side horizontally. This
is an original bounded 2-D width policy, NOT a clinical chin measurement, a
curvature guarantee, commercial calibration, or the legacy small_chin control.

The pinned MediaPipe v1.1.1 oval supplies the complete contiguous lower arc
150-149-176-148-152-377-400-378-379. These measured vertices are not anatomical
labels or visibility evidence. The plane lies below every measured lip vertex;
its center axis has the actual tip152 lateral coordinate. Height is the actual
tip's projected distance below that plane. No extrapolated control is evidence.
https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py

Only Rust computes the inverse. The Python forward formula audits all retained
478 targets, never samples an image or substitutes an inverse. Independent side
amounts meet continuously at the fixed center but may have different one-sided
slopes: this is NOT globally C1. Tip/vertical invariance is audited with explicit
f64 tolerance; no forward-only snapping pretends floating geometry is exact.
"""
from dataclasses import dataclass

import numpy as np

from . import chin_shape_state as S, face_contour_geometry as G
from .face_contour_runtime import require_analysis
from .chin_shape_native import canonical_frame, evaluate as native_evaluate
# Read-only measurement/evidence helpers, never another control's build or ABI.
from .lower_face_runtime import _measured_order, _inside_or_boundary
from .face_size_runtime import (
    _tiles, _tile_points, _source, _measured_inside, _immutable,
)


MAX_POINTS = 65536
REQUIREMENT_ID = 'LNX-REF-PC-32466-C-ed7837df9a'
GAIN = .08
TAIL = .5
LOWER_ARC = (150, 149, 176, 148, 152, 377, 400, 378, 379)
RIGHT_ARC = LOWER_ARC[:4]
LEFT_ARC = LOWER_ARC[5:]
# Factual inner contour from the pinned FACE_LANDMARKS_LIPS connections.
INNER_LIPS = (78, 191, 80, 81, 82, 13, 312, 311, 310, 415,
              308, 324, 318, 402, 317, 14, 87, 178, 88, 95)
LIP_VERTICES = tuple(sorted(set((*G.LIPS, *INNER_LIPS))))
LIMITATION = ('2d_existing_texture_only; measured_lower_oval_not_clinical_chin_anatomy; '
              'signed_horizontal_width_not_guaranteed_roundness_or_curvature; '
              'bilateral_measured_geometry_required_even_for_one_sided_request; '
              'independent_side_center_continuous_not_globally_c1; '
              'incomplete_boundary_and_occlusion_evidence; '
              'below_chin_and_lateral_halo_transports_neighboring_neck_background; '
              'full_support_rectangle_guards_conservatively_include_neutral_side; '
              'prior_edited_points_can_enter_feather_not_global_invariance; '
              'tip_and_vertical_invariance_with_explicit_f64_tolerance; '
              'bounded_floating_inverse_not_exact_real_arithmetic; photographic_acceptance_unrun')


def _smooth(value):
    t = np.clip(value, 0., 1.)
    z = np.minimum(t, 1. - t)
    low = z**3 * (10. + z * (-15. + 6. * z))
    return np.where(t <= .5, low, 1. - low)


def _forward_delta(points, parameters):
    """Forward-only target audit; NEVER an inverse or image-sampling fallback."""
    local = points - parameters[:2]
    # Match the native scalar projection order without a centerline snap.
    u = local[:, 0] * parameters[2] + local[:, 1] * parameters[3]
    t = (local[:, 0] * parameters[4] + local[:, 1] * parameters[5]) / parameters[6]
    inner, outer, left, right = parameters[7:]
    lateral = _smooth((outer - np.abs(u)) / (outer - inner))
    lateral[np.abs(u) >= outer] = 0.
    vertical = np.zeros(len(points), np.float64)
    rising = (t > 0.) & (t < 1.)
    falling = (t >= 1.) & (t < 1. + TAIL)
    vertical[rising] = _smooth(t[rising])
    vertical[falling] = _smooth((1. + TAIL - t[falling]) / TAIL)
    amount = np.where(u > 0., left, np.where(u < 0., right, 0.))
    distance = -(((GAIN * u) * amount) * vertical) * lateral
    return distance[:, None] * parameters[2:4]


def _measured_chin(lm, right, down, width):
    """Require ordered actual lower-oval and lip geometry, without repairing it."""
    _measured_order(lm, right, down, width)
    lips = lm[list(G.LIPS)]
    if not np.all(_inside_or_boundary(lm[list(INNER_LIPS)], lips, max(.25, .001 * width))):
        raise ValueError('Chin shape inner lip vertices leave the measured outer lip polygon')
    tip = lm[152]
    tip_v = (lm - tip) @ down
    lip_margin = max(1., .01 * width)
    plane_from_tip = float(np.max(tip_v[list(LIP_VERTICES)])) + lip_margin
    height = -plane_from_tip
    if not max(16., .08 * width) < height < .50 * width:
        raise ValueError('Chin shape has an unresolved measured below-lip-to-tip interval')
    origin = tip - height * down
    u, v = (lm - origin) @ right, (lm - origin) @ down
    epsilon = np.finfo(np.float64).eps * max(1., width, float(np.max(np.abs(lm)))) * 32
    if (abs(float(u[152])) > epsilon or abs(float(v[152]) - height) > epsilon
            or np.any(v[list(LIP_VERTICES)] > -lip_margin + epsilon)):
        raise ValueError('Chin shape plane does not protect every measured lip vertex or actual tip axis')
    arc_u, arc_v = u[list(LOWER_ARC)], v[list(LOWER_ARC)]
    step = max(.2, .001 * width)
    if (np.any(np.diff(arc_u) <= max(.5, .003 * width))
            or np.any(np.diff(arc_v[:5]) <= step)
            or np.any(np.diff(arc_v[4:]) >= -step)
            or np.any(arc_v < .10 * height) or np.any(arc_v > height + epsilon)
            or not u[148] < -max(1., .005 * width) < max(1., .005 * width) < u[377]
            or not .25 * width < float(np.ptp(arc_u)) < .90 * width):
        raise ValueError('Chin shape requires the complete ordered measured lower-oval arc')
    padding = max(2., .025 * width)
    inner = float(np.max(np.abs(u[v > 0.]))) + padding
    outer = 2. * inner
    if not np.isfinite(outer) or inner <= 0. or np.any(np.abs(arc_u) >= inner):
        raise ValueError('Chin shape cannot enclose its measured moving oval in the lateral core')
    return origin, height, inner, outer, u, v, lip_margin, padding


def _moving(points, origin, right, down, height, outer, recipe):
    local = points - origin
    u, v = local @ right, local @ down
    return ((v > 0.) & (v < (1. + TAIL) * height) & (np.abs(u) < outer)
            & (((u > 0.) & (recipe['left'] != 0.))
               | ((u < 0.) & (recipe['right'] != 0.))))


def _chin_segment_support(a, b, center, width, oval, source, skin, excluded,
                          origin, right, down, height, outer, recipe):
    """Actual inset strip, restricted to the requested moving half-plane(s).

    The strip/ratios follow the common measured evidence policy. Restricting
    the strip, not the field, avoids demanding untouched-side skin at tip152.
    No missing pixels are interpolated, invented, or counted as evidence.
    """
    edge = b - a
    length = float(np.linalg.norm(edge))
    if length < .5:
        raise ValueError('Chin shape has a degenerate measured moving-oval segment')
    inward = np.array([-edge[1], edge[0]]) / length
    if inward @ (center - (a + b) * .5) < 0.:
        inward = -inward
    near, far = max(.8, width * .012), max(3., width * .07)
    poly = np.array([a + near * inward, b + near * inward,
                     b + far * inward, a + far * inward])
    low, high = np.floor(poly.min(0) - 1).astype(int), np.ceil(poly.max(0) + 2).astype(int)
    h, w = source.shape[:2]
    if np.any(low < 1) or np.any(high > [w - 1, h - 1]):
        raise ValueError('Chin shape clipped measured moving-oval skin support')
    count = inside_count = visible_count = observed = 0
    total = total2 = 0.
    for ys, xs in _tiles(low, high):
        points = _tile_points(ys, xs)
        selected = G.polygon_inside(points, poly) & _moving(points, origin, right, down, height, outer, recipe)
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
        raise ValueError('Chin shape lacks actual moving-oval strip skin/RGB support')
    return observed


def _chin_support(lm, center, origin, right, down, height, width, source, skin, excluded, recipe, outer):
    """Observe requested-side lower-chin sectors and real skin beside actual vertices.

    Pixel neighborhoods are evidence probes, not synthetic anatomy. Every probe
    is clipped to the measured oval, not padded with generated or halo samples.
    Each requested sector/probe needs independent skin/RGB ratio and variation.
    The full requested moving oval, not just subsets, receives the occluder veto.
    The inactive side contributes geometry, never invented active evidence.
    """
    oval = lm[list(G.FACE_OVAL)]
    inset = center + .96 * (oval - center)
    low, high = np.floor(oval.min(0)).astype(int), np.ceil(oval.max(0)).astype(int) + 1
    counts, observed = np.zeros(4, np.int64), np.zeros(4, np.int64)
    totals, totals2 = np.zeros(4, np.float64), np.zeros(4, np.float64)
    radius = max(3., .025 * width)
    required = np.array([recipe['right'] != 0., recipe['left'] != 0.] * 2)
    required_probes = np.array([recipe['right'] != 0.] * 4 + [True] + [recipe['left'] != 0.] * 4)
    probe_counts, probe_observed = np.zeros(len(LOWER_ARC), np.int64), np.zeros(len(LOWER_ARC), np.int64)
    probe_totals, probe_totals2 = np.zeros(len(LOWER_ARC), np.float64), np.zeros(len(LOWER_ARC), np.float64)
    for ys, xs in _tiles(low, high):
        points = _tile_points(ys, xs)
        local = points - origin
        u, v = local @ right, local @ down
        inside = G.polygon_inside(points, oval)
        moving = inside & _moving(points, origin, right, down, height, outer, recipe)
        if np.any(moving & (excluded[ys, xs].ravel() >= .15)):
            raise ValueError('Chin shape refuses a known occluder inside its measured moving oval')
        eligible = G.polygon_inside(points, inset) & moving & (v < height)
        sectors = (u >= 0.).astype(np.int8) + 2 * (v >= .5 * height).astype(np.int8)
        luma = source[ys, xs].reshape(-1, 3) @ np.array([.2126, .7152, .0722])
        usable = (skin[ys, xs].ravel() >= .45) & (luma > .006) & (luma < .994)
        for sector in range(4):
            selected = eligible & (sectors == sector)
            counts[sector] += np.count_nonzero(selected)
            sample = luma[selected & usable]
            observed[sector] += len(sample)
            totals[sector] += float(np.sum(sample))
            totals2[sector] += float(sample @ sample)
        for index, landmark in enumerate(LOWER_ARC):
            if not required_probes[index]:
                continue
            selected = moving & (np.linalg.norm(points - lm[landmark], axis=1) <= radius)
            probe_counts[index] += np.count_nonzero(selected)
            sample = luma[selected & usable]
            probe_observed[index] += len(sample)
            probe_totals[index] += float(np.sum(sample))
            probe_totals2[index] += float(sample @ sample)
    divisor = np.maximum(1, observed)
    variance = np.maximum(0., totals2 / divisor - (totals / divisor)**2)
    if (np.any(counts[required] < max(16., width * width * .001))
            or np.any(observed[required] < .85 * counts[required]) or np.any(variance[required] < .0025**2)):
        raise ValueError('Chin shape lacks independent skin/RGB evidence in requested lower-chin sectors')
    divisor = np.maximum(1, probe_observed)
    variance = np.maximum(0., probe_totals2 / divisor - (probe_totals / divisor)**2)
    if (np.any(probe_counts[required_probes] < 6)
            or np.any(probe_observed[required_probes] < .90 * probe_counts[required_probes])
            or np.any(variance[required_probes] < .0025**2)):
        raise ValueError('Chin shape lacks local source skin/RGB beside requested measured lower-arc vertices')
    return tuple(int(value) for value in observed), tuple(int(value) for value in probe_observed)


def _lip_support(lm, down, width, source, excluded):
    """Require actual lower-lip RGB; skin-class exemption is not an occlusion exemption."""
    lips = lm[list(G.LIPS)]
    low, high = np.floor(lips.min(0)).astype(int), np.ceil(lips.max(0)).astype(int) + 1
    h, w = source.shape[:2]
    if np.any(low < 1) or np.any(high > [w - 1, h - 1]):
        raise ValueError('Chin shape clipped measured lower-lip evidence')
    # A plane through measured inner-lip midpoint selects real pixels only.
    # It inserts no landmarks and imposes no opening on coincident closed lips.
    middle = (lm[13] + lm[14]) * .5
    count = observed = 0
    total = total2 = 0.
    for ys, xs in _tiles(low, high):
        points = _tile_points(ys, xs)
        inside = G.polygon_inside(points, lips)
        if np.any(inside & (excluded[ys, xs].ravel() >= .15)):
            raise ValueError('Chin shape refuses a known occluder at its measured lips')
        selected = inside & ((points - middle) @ down >= 0.)
        luma = source[ys, xs].reshape(-1, 3) @ np.array([.2126, .7152, .0722])
        sample = luma[selected & (luma > .006) & (luma < .994)]
        count += int(np.count_nonzero(selected))
        observed += len(sample)
        total += float(np.sum(sample)); total2 += float(sample @ sample)
    variance = max(0., total2 / max(1, observed) - (total / max(1, observed))**2)
    if count < max(12., width * width * .0002) or observed < .90 * count or variance < .0025**2:
        raise ValueError('Chin shape lacks real measured lower-lip RGB evidence')
    return observed


@dataclass(frozen=True, init=False)
class ChinShapeField:
    """Immutable compact horizontal native pullback, with source-target audits."""
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
                raise ValueError('Chin shape needs finite exact-shape float64 ' + label)
        if (type(shape) is not tuple or len(shape) != 2
                or any(type(n) is not int or n < 2 for n in shape)):
            raise ValueError('Chin shape needs a two-dimensional source extent')
        if (type(facts) is not dict or any(type(k) is not str or type(v) not in
                (str, int, float, bool, type(None)) for k, v in facts.items())
                or any(type(v) is float and not np.isfinite(v) for v in facts.values())):
            raise ValueError('Chin shape facts must contain immutable finite scalar values')
        object.__setattr__(self, 'shape', shape)
        object.__setattr__(self, 'state', _immutable(parameters))
        object.__setattr__(self, 'source_landmarks', _immutable(landmarks))
        object.__setattr__(self, 'target_landmarks', _immutable(target))
        object.__setattr__(self, '_fact_items', tuple(facts.items()))
        expected = _forward_delta(self.source_landmarks, self.state)
        if not np.array_equal(self.source_landmarks + expected, self.target_landmarks):
            raise ValueError('Chin shape targets differ from the full requested forward operation')
        actual = self.evaluate(self.target_landmarks)
        epsilon = np.finfo(np.float64).eps * max(shape) * 32
        local = self.source_landmarks - self.state[:2]
        u, v = local @ self.state[2:4], local @ self.state[4:6]
        center = np.abs(u) <= epsilon
        motion, error = np.linalg.norm(expected, axis=1), np.linalg.norm(actual - expected, axis=1)
        # Only the numerical center sliver has an absolute tolerance. No active
        # measured side can exploit it to accept zero/wrong/attenuated strength.
        if (np.any(error[~center] > motion[~center] * 1e-8)
                or np.any(actual[(motion == 0.) & ~center] != 0.)
                or np.any(error[center] > epsilon)):
            raise ValueError('Chin shape native inverse differs from the full requested amount')
        if not np.allclose(self.target_landmarks - actual, self.source_landmarks, rtol=0., atol=epsilon):
            raise ValueError('Chin shape targets do not pull back to their actual measured source')
        target_v = (self.target_landmarks - self.state[:2]) @ self.state[4:6]
        if (np.any(np.abs(actual @ self.state[4:6]) > epsilon)
                or np.any(np.abs(target_v - v) > epsilon)):
            raise ValueError('Chin shape changed measured vertical coordinates')
        if (abs(float(u[152])) > epsilon or abs(float(v[152]) - self.state[6]) > epsilon
                or np.linalg.norm(self.target_landmarks[152] - self.source_landmarks[152]) > epsilon
                or np.linalg.norm(actual[152]) > epsilon):
            raise ValueError('Chin shape changed or replaced actual tip152')
        if (np.any(v[list(LIP_VERTICES)] >= 0.)
                or not np.array_equal(self.target_landmarks[list(LIP_VERTICES)], self.source_landmarks[list(LIP_VERTICES)])
                or np.any(actual[list(LIP_VERTICES)] != 0.)):
            raise ValueError('Chin shape changed measured lips or failed to protect their plane')
        upper = v <= 0.
        if np.any(actual[upper] != 0.) or not np.array_equal(self.target_landmarks[upper], self.source_landmarks[upper]):
            raise ValueError('Chin shape changed the protected upper half-plane')
        target_u = (self.target_landmarks - self.state[:2]) @ self.state[2:4]
        for ids, amount, sign in ((LEFT_ARC, self.state[9], 1.), (RIGHT_ARC, self.state[10], -1.)):
            rows = list(ids)
            if (np.any(sign * u[rows] <= epsilon) or np.any(v[rows] <= 0.)
                    or np.any(v[rows] >= (1. + TAIL) * self.state[6])
                    or np.any(np.abs(u[rows]) >= self.state[7])):
                raise ValueError('Chin shape cannot audit both actual measured chin sides')
            width_change = sign * (target_u[rows] - u[rows])
            if amount == 0.:
                side = sign * u > epsilon
                if np.any(actual[side] != 0.) or not np.array_equal(self.target_landmarks[side], self.source_landmarks[side]):
                    raise ValueError('Chin shape moved the unrequested subject side')
            elif ((amount > 0. and np.any(width_change >= 0.))
                  or (amount < 0. and np.any(width_change <= 0.))):
                raise ValueError('Chin shape requested sign did not change every measured side width')

    @property
    def parameters(self):
        return self.state

    @property
    def facts(self):
        return {'chin_shape': dict(self._fact_items)}

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError('Chin shape evaluation needs finite Nx2 pixel coordinates')
        out = np.empty_like(points)
        for start in range(0, len(points), MAX_POINTS):
            q = points[start:start + MAX_POINTS]
            if not np.isfinite(q).all():
                raise ValueError('Chin shape evaluation needs finite Nx2 pixel coordinates')
            value = native_evaluate(q, self.state)
            if (type(value) is not np.ndarray or value.dtype != np.float64
                    or value.shape != q.shape or not np.isfinite(value).all()):
                raise ValueError('Chin shape native inverse violated its finite float64 output contract')
            out[start:start + len(q)] = value
        return out

    def resident_bytes(self):
        return self.state.nbytes + self.source_landmarks.nbytes + self.target_landmarks.nbytes + 3072


def build(landmarks, recipe, source, excluded, *, backend, analysis, protected_boxes=()):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return None
    if backend != 'mediapipe':
        raise ValueError('Chin shape refuses placeholder, template or unverified face geometry')
    _source(source)
    shape = source.shape[:2]
    skin = require_analysis(landmarks, analysis, shape, excluded)
    lm = G.pixels(np.asarray(analysis['landmarks'], dtype='<f4'), shape)
    measured_right, up, center, width = G.frame(lm)
    right, down = (np.asarray(axis, dtype=np.float64) for axis in canonical_frame(measured_right, -up))
    oval = lm[list(G.FACE_OVAL)]
    _measured_inside(lm, oval, width)
    origin, height, inner, outer, u, v, margin, padding = _measured_chin(lm, right, down, width)
    parameters = np.concatenate((origin, right, down, [height, inner, outer, recipe['left'], recipe['right']]))
    target = lm + _forward_delta(lm, parameters)
    for side, ids in (('left', LEFT_ARC), ('right', RIGHT_ARC)):
        if recipe[side] and np.any(np.all(target[list(ids)] == lm[list(ids)], axis=1)):
            raise ValueError('Chin shape nonzero side amount is below representable measured geometry precision')
    # Fixed support edges and monotonic horizontal map make this COMPLETE
    # rotated rectangle invariant. Never clip it or attenuate an unsafe request.
    corners = np.array([origin + x * right + y * down for x in (-outer, outer)
                        for y in (0., (1. + TAIL) * height)])
    low, high = corners.min(0), corners.max(0)
    h, w = shape
    if np.any(low < 1.) or np.any(high > [w - 2, h - 2]):
        raise ValueError('Chin shape complete influence bounding box is clipped by the source frame')
    boxes = G._boxes(protected_boxes, shape)
    if any(np.all(high >= box[:2] - 1.) and np.all(low <= box[2:] + 1.) for box in boxes):
        raise ValueError('Chin shape complete influence bounding box touches another retained face')
    boundary_count = boundary_segments = 0
    oval_u, oval_v = u[list(G.FACE_OVAL)], v[list(G.FACE_OVAL)]
    epsilon = np.finfo(np.float64).eps * max(shape) * 32
    for index, (a, b) in enumerate(zip(oval, np.roll(oval, -1, axis=0))):
        following = (index + 1) % len(oval)
        touches_side = ((recipe['left'] != 0. and max(oval_u[index], oval_u[following]) > epsilon)
                        or (recipe['right'] != 0. and min(oval_u[index], oval_u[following]) < -epsilon))
        if max(oval_v[index], oval_v[following]) <= 0. or not touches_side:
            continue
        count = _chin_segment_support(a, b, center, width, oval, source, skin, excluded,
                                      origin, right, down, height, outer, recipe)
        boundary_count += count
        boundary_segments += 1
    sectors, probes = _chin_support(lm, center, origin, right, down, height, width, source, skin, excluded, recipe, outer)
    lip_count = _lip_support(lm, down, width, source, excluded)
    maximum = max(abs(recipe['left']), abs(recipe['right']))
    facts = {'control': 'chin_shape', 'requirement_id': REQUIREMENT_ID,
             'requested': True, 'applied': True, 'reason': None,
             'linked': recipe['linked'], 'left': recipe['left'], 'right': recipe['right'],
             'left_requested': recipe['left'] != 0., 'right_requested': recipe['right'] != 0.,
             'left_applied': recipe['left'] != 0., 'right_applied': recipe['right'] != 0.,
             'gain': GAIN, 'tail_ratio': TAIL, 'chin_proxy_index': 152,
             'measured_lip_plane_to_tip_interval_px': height, 'lip_margin_px': margin,
             'measured_lateral_padding_px': padding, 'outer_inner_ratio': 2.,
             'boundary_support_px': boundary_count, 'boundary_segments': boundary_segments,
             'upper_subject_right_skin_rgb_px': sectors[0], 'upper_subject_left_skin_rgb_px': sectors[1],
             'lower_subject_right_skin_rgb_px': sectors[2], 'lower_subject_left_skin_rgb_px': sectors[3],
             'lower_arc_probe_support_px': sum(probes), 'lower_arc_probe_count': sum(value > 0 for value in probes),
             'lower_lip_rgb_px': lip_count, 'protected_lip_vertices': len(LIP_VERTICES),
             'audited_retained_landmarks': 478, 'audited_lower_arc': '-'.join(map(str, LOWER_ARC)),
             'minimum_forward_horizontal_slope_bound': 1. - GAIN * 3.75 * maximum,
             'maximum_forward_horizontal_slope_bound': 1. + GAIN * 3.75 * maximum,
             'tip_vertical_audit_tolerance_px': float(epsilon),
             'method': 'native_bracketed_monotone_horizontal_chin_taper_inverse',
             'core_scope': 'retained_measured_chin_not_arbitrary_prior_edited_points',
             'evidence': 'requested_moving_oval_strips_veto_independent_chin_sectors_actual_arc_probes_lower_lip_rgb',
             'limitation': LIMITATION}
    return ChinShapeField(parameters, lm, target, shape, facts)
