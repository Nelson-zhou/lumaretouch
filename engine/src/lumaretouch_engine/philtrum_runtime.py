# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-owned nose-safe nose-to-mouth gap length. AUTHORED / UNRUN.

LNX-REF-PC-32466-C-2605502c27 人中 follows negative-shortens / positive-lengthens
at https://wiki.pixcakeai.com/guide/9405.html . The .08 gain, measured planes,
support and admission thresholds below are original bounded 2-D policies, not
the commercial solver, clinical philtrum measurement or semantic segmentation.

The pinned MediaPipe v1.1.1 FACE_LANDMARKS_NOSE union has 24 vertices, NOT the
shorter legacy G.NOSE set. All 24 stay above the fixed plane; all 40 official
lip vertices stay below the moving plane. Origin uses actual nose2's lateral
coordinate. H is the measured, margin-trimmed gap, never a guessed landmark.
https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py

The full-width rise also changes surrounding cheek-band texture. Every retained
source point below the lip-safe plane translates equally through the padded
lower-face plateau, including all lips and chin152. The tail moves neighboring
neck/background. A previous edit can relocate points into a feather; none of
these retained-source guarantees promises global invariance after composition.

The NEW thin bridge alone calls the unchanged original mid_face Rust primitive.
Python only audits the forward targets; it never computes an inverse or samples
an image. No RGB, mask, dense field, analysis producer or invented anatomy is
retained. Real-image quality, admission prevalence and photographic parity are
unmeasured. No imports, tests, builds or inference ran while authoring.
"""
from dataclasses import dataclass

import numpy as np

from . import philtrum_state as S, face_contour_geometry as G
from .philtrum_native import canonical_frame, evaluate as native_evaluate
from .face_contour_runtime import require_analysis
# Read-only validation/evidence helpers, never another operation's builder or ABI.
from .lower_face_runtime import _measured_order, _inside_or_boundary, _feature_support
from .face_size_runtime import (
    _tiles, _tile_points, _source, _measured_inside, _immutable,
)


MAX_POINTS = 65536
REQUIREMENT_ID = 'LNX-REF-PC-32466-C-2605502c27'
GAIN = .08
NOSE_VERTICES = (168, 6, 197, 195, 5, 4, 1, 19, 94, 2, 98, 97, 326, 327,
                 294, 278, 344, 440, 275, 45, 220, 115, 48, 64)
INNER_LIPS = (78, 191, 80, 81, 82, 13, 312, 311, 310, 415,
              308, 324, 318, 402, 317, 14, 87, 178, 88, 95)
LIP_VERTICES = tuple(sorted(set((*G.LIPS, *INNER_LIPS))))
LIMITATION = ('2d_existing_texture_only; measured_nose_to_mouth_gap_not_clinical_philtrum_anatomy; '
              'central_corridor_is_observation_policy_not_philtrum_segmentation; '
              'full_width_rising_band_also_changes_surrounding_cheeks; '
              'incomplete_boundary_and_occlusion_evidence; '
              'below_chin_and_lateral_halo_transports_neighboring_neck_background; '
              'full_support_rectangle_guard_is_conservative; '
              'prior_edited_points_can_enter_feather_not_global_nose_or_lip_invariance; '
              'canonical_frame_roundoff_not_bitwise_real_axis_identity; '
              'bounded_floating_inverse_not_exact_real_arithmetic; '
              'short_gap_native_plateau_limit_refusal_prevalence_unmeasured; photographic_acceptance_unrun')


def _smooth(value):
    t = np.clip(value, 0., 1.)
    z = np.minimum(t, 1. - t)
    low = z**3 * (10. + z * (-15. + 6. * z))
    return np.where(t <= .5, low, 1. - low)


def _forward_delta(points, parameters):
    """Forward-only retained-target audit, NEVER an inverse/image fallback."""
    local = points - parameters[:2]
    u = local[:, 0] * parameters[2] + local[:, 1] * parameters[3]
    t = (local[:, 0] * parameters[4] + local[:, 1] * parameters[5]) / parameters[6]
    inner, outer, plateau, tail, amount = parameters[7:]
    lateral = _smooth((outer - np.abs(u)) / (outer - inner))
    lateral[np.abs(u) >= outer] = 0.
    vertical = np.zeros(len(points), np.float64)
    rising, flat = (t > 0.) & (t < 1.), (t >= 1.) & (t <= plateau)
    falling = (t > plateau) & (t < plateau + tail)
    vertical[rising] = _smooth(t[rising])
    vertical[flat] = 1.
    vertical[falling] = _smooth((plateau + tail - t[falling]) / tail)
    distance = (((GAIN * parameters[6]) * amount) * lateral) * vertical
    return distance[:, None] * parameters[4:6]


def _measured_gap(lm, right, down, width):
    """Use all actual nose/lip vertices; refuse unresolved gaps or core limits."""
    nose, lower_height, _, nose_v = _measured_order(lm, right, down, width)
    if not np.all(_inside_or_boundary(lm[list(INNER_LIPS)], lm[list(G.LIPS)],
                                     max(.25, .001 * width))):
        raise ValueError('Philtrum inner lip vertices leave the measured outer lip polygon')
    margin = max(1., .01 * width)
    upper_plane = float(np.max(nose_v[list(NOSE_VERTICES)])) + margin
    lower_plane = float(np.min(nose_v[list(LIP_VERTICES)])) - margin
    height = lower_plane - upper_plane
    if not max(4., .02 * width) < height < .35 * width:
        raise ValueError('Philtrum has an unresolved or too-short measured all-nose/all-lip gap')
    origin = nose + upper_plane * down
    u, v = (lm - origin) @ right, (lm - origin) @ down
    epsilon = np.finfo(np.float64).eps * max(1., width, float(np.max(np.abs(lm)))) * 32
    eyes = [index for ids in G.EYES for index in ids]
    if (abs(float(u[2])) > epsilon
            or np.any(v[list(NOSE_VERTICES)] > -margin + epsilon)
            or np.any(v[list(LIP_VERTICES)] < height + margin - epsilon)
            or np.any(v[eyes] >= 0.)):
        raise ValueError('Philtrum planes do not protect the complete measured nose, eyes and lips')
    lower = v >= height
    if not lower[152] or np.any(~lower[list(LIP_VERTICES)]) or np.any(lower[list(NOSE_VERTICES)]):
        raise ValueError('Philtrum cannot resolve its complete measured lower-face source set')
    padding = max(2., .025 * width)
    plateau = (float(np.max(v[lower])) + padding) / height
    tail = max(.25, .5 * (plateau - 1.))
    # A short real gap may make P > 8. Never enlarge H, shift a measured plane,
    # drop lower vertices, attenuate amount or widen the inherited native bounds.
    if not 1.25 <= plateau <= 8. or not .25 <= tail <= 4.:
        raise ValueError('Philtrum measured gap/lower plateau exceeds unchanged native P [1.25,8] or tail [.25,4] limits')
    inner = float(np.max(np.abs(u[v > 0.]))) + padding
    outer = inner + .25 * width
    if (not np.isfinite(outer) or not 0. < inner < outer
            or np.any(np.abs(u[lower]) >= inner) or np.any(v[lower] >= plateau * height)):
        raise ValueError('Philtrum cannot enclose every retained lower-face source point in its flat plateau')
    # This is an actual source-pixel corridor shared by measured nose/lip spans,
    # not a claimed anatomical polygon or substitute landmarks.
    gap_left = max(float(np.min(u[list(NOSE_VERTICES)])), float(np.min(u[list(LIP_VERTICES)]))) + margin
    gap_right = min(float(np.max(u[list(NOSE_VERTICES)])), float(np.max(u[list(LIP_VERTICES)]))) - margin
    if not gap_left < -max(2., .01 * width) < max(2., .01 * width) < gap_right:
        raise ValueError('Philtrum lacks an independently measurable central nose/lip overlap corridor')
    return (origin, height, inner, outer, plateau, tail, u, v, lower,
            margin, padding, gap_left, gap_right, lower_height)


def _moving_segment_support(a, b, center, width, oval, source, skin, excluded,
                            origin, right, down, height, outer, plateau, tail):
    """Observe actual inset oval strips only where this source field moves.

    Intersecting an evidence strip with known support neither clips the field
    nor manufactures anatomy. Untouched portions above the nose-safe plane do
    not establish, or unnecessarily veto, the moving portion's skin evidence.
    """
    edge = b - a
    length = float(np.linalg.norm(edge))
    if length < .5:
        raise ValueError('Philtrum has a degenerate measured moving-oval segment')
    inward = np.array([-edge[1], edge[0]]) / length
    if inward @ (center - (a + b) * .5) < 0.:
        inward = -inward
    near, far = max(.8, width * .012), max(3., width * .07)
    poly = np.array([a + near * inward, b + near * inward,
                     b + far * inward, a + far * inward])
    low, high = np.floor(poly.min(0) - 1).astype(int), np.ceil(poly.max(0) + 2).astype(int)
    h, w = source.shape[:2]
    if np.any(low < 1) or np.any(high > [w - 1, h - 1]):
        raise ValueError('Philtrum clipped measured moving-oval skin support')
    count = inside_count = visible_count = observed = 0
    total = total2 = 0.
    for ys, xs in _tiles(low, high):
        points = _tile_points(ys, xs)
        local = points - origin
        u, v = local @ right, local @ down
        moving = (v > 0.) & (v < (plateau + tail) * height) & (np.abs(u) < outer)
        selected = G.polygon_inside(points, poly) & moving
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
        raise ValueError('Philtrum lacks actual moving-oval strip skin/RGB support')
    return observed


def _source_support(lm, center, origin, right, down, height, width,
                    source, skin, excluded, outer, plateau, tail, gap_left, gap_right):
    """Observe gap, surrounding moving band and lower face INDEPENDENTLY.

    Each region needs its own four skin/RGB quadrants and local variance. Gap
    counts scale with its measured area, never cheek-width squared; cheeks or
    lower-face texture cannot stand in for the central gap. No skin exemption
    applies in the gap. Lips have separate RGB evidence and no occlusion bypass.
    """
    oval = lm[list(G.FACE_OVAL)]
    inset = center + .96 * (oval - center)
    low, high = np.floor(oval.min(0)).astype(int), np.ceil(oval.max(0)).astype(int) + 1
    counts, observed = np.zeros((3, 4), np.int64), np.zeros((3, 4), np.int64)
    totals, totals2 = np.zeros((3, 4), np.float64), np.zeros((3, 4), np.float64)
    lower_end = float((lm[152] - origin) @ down)
    if lower_end <= height:
        raise ValueError('Philtrum has no measurable lower-face source interior')
    for ys, xs in _tiles(low, high):
        points = _tile_points(ys, xs)
        local = points - origin
        u, v = local @ right, local @ down
        inside = G.polygon_inside(points, oval)
        moving = inside & (v > 0.) & (v < (plateau + tail) * height) & (np.abs(u) < outer)
        if np.any(moving & (excluded[ys, xs].ravel() >= .15)):
            raise ValueError('Philtrum refuses a known occluder inside its measured moving oval')
        band = (v > 0.) & (v < height)
        gap = band & (u > gap_left) & (u < gap_right)
        if np.any(gap & ~inside):
            raise ValueError('Philtrum central measured gap corridor leaves the source oval')
        inset_inside = G.polygon_inside(points, inset)
        surrounding = band & inset_inside & ((u <= gap_left) | (u >= gap_right))
        lower = (inset_inside & (v >= height) & (v <= lower_end)
                 & ~G.polygon_inside(points, lm[list(G.LIPS)]))
        band_sector = (u >= 0.).astype(np.int8) + 2 * (v >= .5 * height).astype(np.int8)
        lower_sector = ((u >= 0.).astype(np.int8)
                        + 2 * (v >= .5 * (height + lower_end)).astype(np.int8))
        luma = source[ys, xs].reshape(-1, 3) @ np.array([.2126, .7152, .0722])
        usable = (skin[ys, xs].ravel() >= .45) & (luma > .006) & (luma < .994)
        for region, eligible, sectors in ((0, gap, band_sector),
                                          (1, surrounding, band_sector),
                                          (2, lower, lower_sector)):
            for sector in range(4):
                selected = eligible & (sectors == sector)
                counts[region, sector] += np.count_nonzero(selected)
                sample = luma[selected & usable]
                observed[region, sector] += len(sample)
                totals[region, sector] += float(np.sum(sample))
                totals2[region, sector] += float(sample @ sample)
    divisor = np.maximum(1, observed)
    variance = np.maximum(0., totals2 / divisor - (totals / divisor)**2)
    gap_area = (gap_right - gap_left) * height
    thresholds = (max(4., .04 * gap_area), max(8., .01 * width * height),
                  max(16., .001 * width * width))
    for region, label in enumerate(('central gap', 'surrounding moving band', 'lower face')):
        ratio = .90 if region == 0 else .85
        if (np.any(counts[region] < thresholds[region])
                or np.any(observed[region] < ratio * counts[region])
                or np.any(variance[region] < .0025**2)):
            raise ValueError('Philtrum lacks independent actual skin/RGB evidence in all four ' + label + ' sectors')
    return tuple(tuple(int(value) for value in row) for row in observed)


@dataclass(frozen=True, init=False)
class PhiltrumField:
    """Immutable native pullback with all-478 retained source/target audits."""
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
                raise ValueError('Philtrum needs finite exact-shape float64 ' + label)
        if (type(shape) is not tuple or len(shape) != 2
                or any(type(n) is not int or n < 2 for n in shape)):
            raise ValueError('Philtrum needs a two-dimensional source extent')
        if (parameters[6] <= 0. or not 0. < parameters[7] < parameters[8]
                or not 1.25 <= parameters[9] <= 8. or not .25 <= parameters[10] <= 4.
                or parameters[10] != max(.25, .5 * (parameters[9] - 1.))
                or not -1. <= parameters[11] <= 1. or parameters[11] == 0.):
            raise ValueError('Philtrum requires its measured gap, unchanged plateau/tail bounds and active signed amount')
        canonical_frame(parameters[2:4], parameters[4:6])
        if (type(facts) is not dict or any(type(k) is not str or type(v) not in
                (str, int, float, bool, type(None)) for k, v in facts.items())
                or any(type(v) is float and not np.isfinite(v) for v in facts.values())):
            raise ValueError('Philtrum facts must contain immutable finite scalar values')
        # Parameters are derived from this exact source, not target-picked
        # membership or caller-supplied planes that merely look plausible.
        measured_right, up, _, width = G.frame(landmarks)
        right, down = (np.asarray(axis, np.float64) for axis in canonical_frame(measured_right, -up))
        measured = _measured_gap(landmarks, right, down, width)
        origin, height, inner, outer, plateau, tail = measured[:6]
        expected_parameters = np.concatenate((origin, right, down, [height, inner, outer, plateau, tail]))
        if not np.array_equal(parameters[:11], expected_parameters):
            raise ValueError('Philtrum parameters differ from the complete retained-source measured gap policy')
        object.__setattr__(self, 'shape', shape)
        object.__setattr__(self, 'state', _immutable(parameters))
        object.__setattr__(self, 'source_landmarks', _immutable(landmarks))
        object.__setattr__(self, 'target_landmarks', _immutable(target))
        object.__setattr__(self, '_fact_items', tuple(facts.items()))
        expected = _forward_delta(self.source_landmarks, self.state)
        if not np.array_equal(self.source_landmarks + expected, self.target_landmarks):
            raise ValueError('Philtrum targets differ from the full requested forward operation')
        epsilon = np.finfo(np.float64).eps * max(shape) * 32
        actual = self.evaluate(self.target_landmarks)
        motion, error = np.linalg.norm(expected, axis=1), np.linalg.norm(actual - expected, axis=1)
        u, v, lower = measured[6:9]
        # Absolute coordinate roundoff is allowed in the rise, not a license to
        # attenuate the plateau amount. Every lower point has the full relative
        # amount audit even for tiny representable requests.
        if (np.any(error > motion * 1e-8 + epsilon)
                or np.any(error[lower] > motion[lower] * 1e-8)
                or np.any(actual[motion == 0.] != 0.)):
            raise ValueError('Philtrum native inverse differs from the full requested amount')
        if not np.allclose(self.target_landmarks - actual, self.source_landmarks, rtol=0., atol=epsilon):
            raise ValueError('Philtrum targets do not pull back to their measured source')
        if np.any(np.abs(actual @ self.state[2:4]) > motion * 1e-10 + epsilon):
            raise ValueError('Philtrum native inverse changed measured head-axis width')
        upper = v <= 0.
        if (np.any(actual[upper] != 0.)
                or not np.array_equal(self.target_landmarks[upper], self.source_landmarks[upper])
                or np.any(v[list(NOSE_VERTICES)] >= 0.)
                or not np.array_equal(self.target_landmarks[list(NOSE_VERTICES)],
                                      self.source_landmarks[list(NOSE_VERTICES)])):
            raise ValueError('Philtrum changed its fixed upper plane or a complete official nose vertex')
        plateau_delta = ((GAIN * height) * self.state[11]) * self.state[4:6]
        if (np.any(~lower[list(LIP_VERTICES)]) or not lower[152]
                or np.any(np.linalg.norm(expected[lower] - plateau_delta, axis=1)
                          > np.linalg.norm(plateau_delta) * 1e-10)):
            raise ValueError('Philtrum did not translate all forty lips and every retained lower-face source point equally')
        before = self.source_landmarks[lower] - self.source_landmarks[0]
        after = self.target_landmarks[lower] - self.target_landmarks[0]
        if not np.allclose(after, before, rtol=0., atol=epsilon):
            raise ValueError('Philtrum changed measured lip shape or lip-to-chin/lower-face relative vectors')
        before_gap = float((self.source_landmarks[0] - self.source_landmarks[2]) @ self.state[4:6])
        after_gap = float((self.target_landmarks[0] - self.target_landmarks[2]) @ self.state[4:6])
        change = (GAIN * height) * self.state[11]
        signed_change = after_gap - before_gap
        if (before_gap <= 0. or (change > 0. and signed_change <= 0.)
                or (change < 0. and signed_change >= 0.)
                or abs((after_gap - before_gap) - change) > epsilon):
            raise ValueError('Philtrum requested sign did not add the measured gap shift to actual nose2-to-lip0 length')

    @property
    def parameters(self):
        return self.state

    @property
    def facts(self):
        return {'philtrum': dict(self._fact_items)}

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError('Philtrum evaluation needs finite Nx2 pixel coordinates')
        out = np.empty_like(points)
        for start in range(0, len(points), MAX_POINTS):
            q = points[start:start + MAX_POINTS]
            if not np.isfinite(q).all():
                raise ValueError('Philtrum evaluation needs finite Nx2 pixel coordinates')
            value = native_evaluate(q, self.state)
            if (type(value) is not np.ndarray or value.dtype != np.float64
                    or value.shape != q.shape or not np.isfinite(value).all()):
                raise ValueError('Philtrum native inverse violated its finite float64 output contract')
            out[start:start + len(q)] = value
        return out

    def resident_bytes(self):
        return self.state.nbytes + self.source_landmarks.nbytes + self.target_landmarks.nbytes + 4096


def build(landmarks, recipe, source, excluded, *, backend, analysis, protected_boxes=()):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return None
    if backend != 'mediapipe':
        raise ValueError('Philtrum refuses placeholder, template or unverified face geometry')
    _source(source)
    shape = source.shape[:2]
    skin = require_analysis(landmarks, analysis, shape, excluded)
    lm = G.pixels(np.asarray(analysis['landmarks'], dtype='<f4'), shape)
    measured_right, up, center, width = G.frame(lm)
    right, down = (np.asarray(axis, dtype=np.float64) for axis in canonical_frame(measured_right, -up))
    oval = lm[list(G.FACE_OVAL)]
    _measured_inside(lm, oval, width)
    (origin, height, inner, outer, plateau, tail, u, v, lower,
     margin, padding, gap_left, gap_right, lower_height) = _measured_gap(lm, right, down, width)
    parameters = np.concatenate((origin, right, down, [height, inner, outer, plateau, tail, recipe['amount']]))
    target = lm + _forward_delta(lm, parameters)
    if np.any(np.all(target[lower] == lm[lower], axis=1)):
        raise ValueError('Philtrum nonzero amount is below representable measured lower-face geometry precision')
    # Monotone fixed support endpoints preserve this COMPLETE rotated rectangle.
    # Do not clip its tail/halo, shrink gain, or omit an unresolved neighbor.
    corners = np.array([origin + x * right + y * down for x in (-outer, outer)
                        for y in (0., (plateau + tail) * height)])
    low, high = corners.min(0), corners.max(0)
    h, w = shape
    if np.any(low < 1.) or np.any(high > [w - 2, h - 2]):
        raise ValueError('Philtrum complete influence bounding box is clipped by the source frame')
    boxes = G._boxes(protected_boxes, shape)
    if any(np.all(high >= box[:2] - 1.) and np.all(low <= box[2:] + 1.) for box in boxes):
        raise ValueError('Philtrum complete influence bounding box touches another retained face')
    boundary_count = boundary_segments = 0
    oval_v = v[list(G.FACE_OVAL)]
    for index, (a, b) in enumerate(zip(oval, np.roll(oval, -1, axis=0))):
        if max(oval_v[index], oval_v[(index + 1) % len(oval)]) <= 0.:
            continue
        boundary_count += _moving_segment_support(a, b, center, width, oval, source, skin, excluded,
                                                  origin, right, down, height, outer, plateau, tail)
        boundary_segments += 1
    support = _source_support(lm, center, origin, right, down, height, width, source, skin, excluded,
                              outer, plateau, tail, gap_left, gap_right)
    nose_count, lip_count = _feature_support(lm, lm[2], width, source, skin, excluded)
    slope = abs(recipe['amount']) * GAIN * 1.875 * max(1., 1. / tail)
    facts = {'control': 'philtrum', 'requirement_id': REQUIREMENT_ID,
             'requested': True, 'applied': True, 'reason': None, 'amount': recipe['amount'],
             'gain': GAIN, 'nose_axis_index': 2, 'upper_lip_proxy_index': 0, 'chin_proxy_index': 152,
             'measured_nose_safe_to_lip_safe_gap_px': height, 'nose_lip_margin_px': margin,
             'actual_nose2_to_lip0_interval_px': float((lm[0] - lm[2]) @ down),
             'actual_nose2_to_lip0_length_change_px': (GAIN * height) * recipe['amount'],
             'measured_nose_to_chin_interval_px': lower_height,
             'measured_plateau_padding_px': padding, 'plateau_end_ratio': plateau, 'tail_ratio': tail,
             'central_gap_axis_min_px': gap_left, 'central_gap_axis_max_px': gap_right,
             'boundary_support_px': boundary_count, 'boundary_segments': boundary_segments,
             'nose_support_px': nose_count, 'lip_support_px': lip_count,
             'audited_retained_landmarks': 478, 'protected_nose_vertices': len(NOSE_VERTICES),
             'rigid_lip_vertices': len(LIP_VERTICES),
             'audited_lower_plateau_landmarks': int(np.count_nonzero(lower)),
             'minimum_forward_vertical_slope_bound': 1. - slope,
             'maximum_forward_vertical_slope_bound': 1. + slope,
             'method': 'new_philtrum_bridge_unchanged_mid_face_native_bracketed_quintic_plateau_inverse',
             'core_scope': 'retained_source_lower_face_not_arbitrary_prior_edited_points',
             'evidence': 'independent_central_gap_and_surrounding_band_and_lower_face_skin_rgb_quadrants_moving_oval_strips_real_lips_occluder_veto',
             'limitation': LIMITATION}
    for name, counts in zip(('central_gap', 'surrounding_band', 'lower_face'), support):
        for label, count in zip(('upper_negative_axis', 'upper_positive_axis',
                                 'lower_negative_axis', 'lower_positive_axis'), counts):
            facts[name + '_' + label + '_skin_rgb_px'] = count
    return PhiltrumField(parameters, lm, target, shape, facts)
