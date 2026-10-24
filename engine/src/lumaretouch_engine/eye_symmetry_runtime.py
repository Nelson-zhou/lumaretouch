# SPDX-License-Identifier: GPL-3.0-or-later
"""Measured source-owned eye symmetry. AUTHORED / UNRUN.

PC-32470 family 2745ac86f5: horizontal a86e5c0175, size 4601eb7797,
reference 118aa67e04; https://wiki.pixcakeai.com/guide/9810.html . The guide's
larger-eye automatic size reference and manual side selection are product
semantics. Forehead10/chin152 roll, bridge-consistency admission, bilateral
midpoint levelling, 16-lid aperture area and isotropic scaling are OUR bounded
2-D policies, not the commercial algorithm or an anatomical diagnosis.

The eye-to-eye/iris axis MUST NOT measure height asymmetry: it would remove the
very difference being corrected. Existing eye_shape evidence is reused ONLY to
veto poor source RGB/known-occluder support, never to supply our correction axis.
Both eyes need evidence even for an explicitly selected reference. All actual
16 lid + 5 iris points of each eye are transported, without copying reference
texture or synthesizing hidden anatomy. The reference is fixed for size only;
horizontal correction, when enabled, moves both eyes equally toward the mean.

The NEW native adapter calls unchanged eye_shape Rust controls. Unchanged
EyeField supplies compact protected inverse TPS and sampled fold admission.
This subclass adds strict requested-control and actual source-footprint audits;
it does NOT replace any old recipe, solve an alternative inverse or sample RGB.
No scale/shift is clipped or attenuated to fit native bounds. Finite numerical
target tolerance and sampled Jacobians are NOT exact interpolation or a global
injectivity proof. Retained-source guarantees are not guarantees after earlier
manual geometry: a composed prefix may have moved texture into the feather.

Canonical ownership authenticates retained landmark bytes and source identity,
not a fictitious equivalence between decoded RGB and an encoded-file SHA-256.
Durable source/producer extents are not the current render grid: the existing
snapshot owner resizes measured masks while retaining normalized landmarks and
evidence. Geometry is rebuilt on each actual RGB grid, never by enlarging a
proxy displacement or corrected RGB into a claimed full-resolution result.
No imports, test collection/execution, builds, inference or photographic checks
ran while authoring; admission prevalence and photographic parity are unmeasured.
"""
from copy import deepcopy
import hashlib

import numpy as np

from . import eye_symmetry_state as S
from .eye_symmetry_native import controls as native_controls, available as native_available
from .eye_shape_geometry import EYES, IRIS, CHAINS, NOSE_PROTECTION, NOSE, LIPS, BROWS, evidence
from .eye_shape_field import EyeField
from .brow_shape_geometry import polygon_inside, pixels
from .ops.deform import BORDER_ANCHORS, dedupe_controls


SIDES = ('left', 'right')
BRIDGE = (168, 6, 197, 195, 5, 4, 1)
ANCHORS = tuple(sorted(set((*NOSE, *NOSE_PROTECTION, *LIPS, *BROWS, 10, 109, 338, 152))))
REQUIREMENT_ID = 'LNX-REF-PC-32470-C-2745ac86f5'
LIMITATION = ('source_owned_2d_existing_texture_only; head_axis_and_midpoint_are_original_policies; '
              'lid_aperture_area_not_eyeball_volume; source_rgb_and_known_occluders_not_complete_visibility; '
              'compact_halo_may_move_neighboring_texture; sampled_jacobians_not_global_injectivity; '
              'numerical_control_tolerance_not_exact_real_arithmetic; '
              'source_protection_not_invariance_after_prior_manual_geometry; '
              'native_bounds_refuse_not_cap; photographic_acceptance_unrun')


def _immutable(value):
    a = np.ascontiguousarray(value, dtype=np.float64)
    return np.frombuffer(a.tobytes(), dtype=np.float64).reshape(a.shape)


def _source(source):
    if (type(source) is not np.ndarray or source.dtype not in (np.float32, np.float64)
            or source.ndim != 3 or source.shape[2] != 3 or min(source.shape[:2]) < 2):
        raise ValueError('Eye symmetry requires actual source-frame float RGB')
    for start in range(0, source.shape[0], 64):
        band = source[start:start + 64]
        if not np.isfinite(band).all() or np.any((band < 0.) | (band > 1.)):
            raise ValueError('Eye symmetry source RGB must be finite and in [0,1]')


def _retained(landmarks, analysis, shape, excluded):
    """Authenticate actual canonical observations without demanding new masks."""
    from .people_state import check_ref, check_evidence
    if type(analysis) is not dict or not {'face_ref', 'evidence', 'landmarks', 'excluded'}.issubset(analysis):
        raise ValueError('Eye symmetry needs retained source-owned analysis')
    check_ref(analysis['face_ref'])
    observation = check_evidence(analysis['evidence'])
    if (observation['status'] != 'verified' or observation['backend'] != 'mediapipe'
            or observation['semantic_model_sha256'] is None):
        raise ValueError('Eye symmetry needs verified detector and known-occluder evidence')
    # check_evidence validates durable positive source dimensions. They need
    # not equal this render grid: snapshot.at_dimensions legitimately retains
    # source evidence while resizing masks and rebuilding normalized geometry.
    canonical = []
    for value in (landmarks, analysis['landmarks']):
        lm = np.asarray(value, dtype='<f4')
        if (lm.shape != (478, 3) or not np.isfinite(lm).all()
                or np.any((lm[:, :2] < 0.) | (lm[:, :2] > 1.))):
            raise ValueError('Eye symmetry requires actual normalized 478x3 landmarks')
        if hashlib.sha256(np.ascontiguousarray(lm).tobytes()).hexdigest() != observation['landmark_digest']:
            raise ValueError('Eye symmetry landmarks differ from exact retained landmark bytes')
        canonical.append(lm)
    retained = analysis['excluded']
    if (type(excluded) is not np.ndarray or type(retained) is not np.ndarray
            or excluded.shape != tuple(shape) or retained.shape != tuple(shape)
            or not np.isfinite(excluded).all() or np.any((excluded < 0.) | (excluded > 1.))
            or not np.array_equal(excluded, retained)):
        raise ValueError('Eye symmetry requires the retained same-source known-occluder field')
    # Float64 perturbations that hash identically must never influence geometry.
    return canonical[1]


def _head_frame(lm):
    """Independent forehead/chin axis with actual ordered bridge consistency."""
    up = lm[10] - lm[152]
    height = float(np.linalg.norm(up))
    if not np.isfinite(height) or height < 64.:
        raise ValueError('Eye symmetry cannot resolve an independent forehead/chin head axis')
    up = up / height
    lateral = np.array([-up[1], up[0]])
    bridge = lm[list(BRIDGE)]
    downward = (lm[10] - bridge) @ up
    sideways = (bridge - lm[10]) @ lateral
    span = float((bridge[0] - bridge[-1]) @ up)
    length = float(np.linalg.norm(bridge[0] - bridge[-1]))
    if (not .08 * height <= span <= .5 * height or length <= 0.
            or span / length < .90 or np.any(np.diff(downward) < -.005 * height)
            or np.any(np.abs(sideways) > .12 * height)
            or not .1 * height < downward[0] < downward[-1] < .85 * height):
        raise ValueError('Eye symmetry nose bridge is inconsistent with its independent head axis')
    return lateral, up, height


def _cross(a, b):
    return float(a[0] * b[1] - a[1] * b[0])


def _area(eye):
    """Actual ordered 16-lid opening, refusing degenerate/self-crossing rings."""
    if eye.shape != (16, 2) or not np.isfinite(eye).all():
        raise ValueError('Eye symmetry requires every actual 16-point lid polygon')
    edges = np.roll(eye, -1, axis=0) - eye
    if np.any(np.linalg.norm(edges, axis=1) < 1e-4):
        raise ValueError('Eye symmetry has duplicate or unresolved lid points')
    for i in range(16):
        a, b = eye[i], eye[(i + 1) % 16]
        for j in range(i + 1, 16):
            if j == i + 1 or (i == 0 and j == 15):
                continue
            c, d = eye[j], eye[(j + 1) % 16]
            if np.any(np.maximum(a, b) < np.minimum(c, d)) or np.any(np.maximum(c, d) < np.minimum(a, b)):
                continue
            if _cross(b - a, c - a) * _cross(b - a, d - a) <= 0. and _cross(d - c, a - c) * _cross(d - c, b - c) <= 0.:
                raise ValueError('Eye symmetry refuses a self-crossing lid opening')
    local = eye - eye.mean(0)
    area = abs(float(np.sum(local[:, 0] * np.roll(local[:, 1], -1)
                            - local[:, 1] * np.roll(local[:, 0], -1)))) * .5
    if not np.isfinite(area) or area < 12.:
        raise ValueError('Eye symmetry has no resolved measured lid-opening area')
    return area


def _measure(lm):
    lateral, up, head_height = _head_frame(lm)
    eyes = {}
    for side in SIDES:
        points = lm[list(EYES[side] + IRIS[side])]
        eye = points[:16]
        center = (eye[0] + eye[8]) * .5
        width = float(np.linalg.norm(eye[0] - eye[8]))
        height = float(np.ptp(eye @ up))
        outward = lateral if side == 'left' else -lateral
        iris_radii = np.linalg.norm(points[17:] - points[16], axis=1)
        if (width < 24. or height < 4. or not .10 * width <= height <= .65 * width
                or float((eye[0] - eye[8]) @ outward) < .75 * width
                or not polygon_inside(points[16, 0], points[16, 1], eye)
                or np.any(iris_radii < 1.) or np.any(iris_radii > .5 * width)):
            raise ValueError('Eye symmetry cannot resolve all 21 actual eye landmarks in its head frame')
        eyes[side] = {'points': points, 'center': center, 'width': width, 'height': height,
                      'area': _area(eye), 'outward': outward}
    separation = float((eyes['left']['center'] - eyes['right']['center']) @ lateral)
    if not .12 * head_height < separation < .8 * head_height:
        raise ValueError('Eye symmetry cannot resolve the two named eyes independently')
    return {'eyes': eyes, 'up': up, 'lateral': lateral, 'head_height': head_height,
            'height_difference': float((eyes['left']['center'] - eyes['right']['center']) @ up)}


def _corrections(measured, recipe):
    eyes = measured['eyes']
    reference = recipe['reference']
    if reference == 'auto':
        # An exact-area tie chooses subject-left deterministically but moves
        # neither eye for size. This does not invent an asymmetry threshold.
        reference = 'left' if eyes['left']['area'] >= eyes['right']['area'] else 'right'
    other = 'right' if reference == 'left' else 'left'
    ratio = float(np.sqrt(eyes[reference]['area'] / eyes[other]['area']))
    if recipe['size'] > 0. and eyes[reference]['area'] != eyes[other]['area'] and ratio == 1.:
        raise ValueError('Eye symmetry unequal measured areas have no representable size ratio')
    change = recipe['size'] * (ratio - 1.)
    scale = 1. + change
    if (recipe['size'] > 0. and ratio != 1. and (change == 0. or scale == 1.)):
        raise ValueError('Eye symmetry size strength is not representable without losing its request')
    difference = measured['height_difference']
    half = (.5 * difference) * recipe['horizontal']
    if recipe['horizontal'] > 0. and difference != 0. and half == 0.:
        raise ValueError('Eye symmetry horizontal strength is not representable')
    scales = {reference: 1., other: float(scale)}
    shifts = {'left': float(-half), 'right': float(half)}
    return reference, scales, shifts


def _boxes(protected_boxes, shape):
    h, w = shape
    result = []
    for value in protected_boxes:
        if (type(value) not in (tuple, list) or len(value) != 4
                or any(type(x) not in (int, float) or not np.isfinite(x) for x in value)
                or not 0. <= value[0] < value[2] <= 1. or not 0. <= value[1] < value[3] <= 1.):
            raise ValueError('Eye symmetry requires actual retained normalized foreign-face boxes')
        result.append(tuple(float(x) for x in value))
    return tuple(result)


def _guard_points(coordinates, shape, boxes):
    if not len(coordinates):
        return
    h, w = shape
    if np.any(coordinates < 1.) or np.any(coordinates > [w - 2, h - 2]):
        raise ValueError('Eye symmetry footprint is outside the genuine source margin')
    for normalized in boxes:
        box = np.asarray(normalized) * [w - 1, h - 1, w - 1, h - 1]
        if np.any(np.all((coordinates >= box[:2] - 1.) & (coordinates <= box[2:] + 1.), axis=1)):
            raise ValueError('Eye symmetry touches another retained face')


class EyeSymmetryField(EyeField):
    """Unchanged protected EyeField TPS, with strict no-hidden-attenuation audit."""

    def __init__(self, P, D, meta, shape):
        self.protected_boxes = _boxes(meta['protected_boxes'], shape)
        self.source_eyes = _immutable(meta['source_eyes'])
        self.target_eyes = _immutable(meta['target_eyes'])
        self.requested_P = _immutable(meta['requested_P'])
        self.requested_D = _immutable(meta['requested_D'])
        super().__init__(P, D, meta, shape)
        actual = self.evaluate(self.requested_P)
        motion = np.hypot(self.requested_D[:, 0], self.requested_D[:, 1])
        difference = actual - self.requested_D
        error = np.hypot(difference[:, 0], difference[:, 1])
        # Moving points have relative tolerance, so tiny requests may NOT hide
        # under an absolute acceptance floor. Zero pins have 1e-7 pixel tolerance.
        # Existing TPS regularization can cause conservative refusals here;
        # numerical admission prevalence is UNRUN, not a reason to weaken this.
        tolerance = np.where(motion > 0., motion * 1e-4, 1e-7)
        if np.any(error > tolerance):
            raise ValueError('Eye symmetry TPS/protection would attenuate the full requested controls')
        self.control_error_px = float(np.max(error, initial=0.))
        self.facts = deepcopy(self.facts)
        for fact in self.facts.values():
            fact['control_error_px'] = self.control_error_px
            fact['control_relative_tolerance'] = 1e-4
            fact['zero_pin_tolerance_px'] = 1e-7
            fact['fold_check'] = 'existing_EyeField_sampled_jacobians_not_global_injectivity'
        # Own retained numeric arrays, never masks, RGB or the caller's analysis.
        self.landmarks = _immutable(self.landmarks)
        self.windows = tuple((_immutable(c), float(r0), float(radius)) for c, r0, radius in self.windows)
        self.protected = tuple(_immutable(poly) for poly in self.protected)
        if self.state is not None:
            self.state = {key: _immutable(value) if isinstance(value, np.ndarray) else value
                          for key, value in self.state.items()}

    def evaluate(self, points):
        X = np.asarray(points, dtype=np.float64)
        if X.ndim != 2 or X.shape[1] != 2 or not np.isfinite(X).all():
            raise ValueError('Eye symmetry needs finite Nx2 evaluation coordinates')
        result = super().evaluate(X)
        active = np.any(result != 0., axis=1)
        _guard_points(X[active], self.shape, self.protected_boxes)
        _guard_points((X - result)[active], self.shape, self.protected_boxes)
        return result

    def resident_bytes(self):
        return (super().resident_bytes() + self.source_eyes.nbytes + self.target_eyes.nbytes
                + self.requested_P.nbytes + self.requested_D.nbytes
                + sum(c.nbytes for c, _, _ in self.windows) + 128 * len(self.protected_boxes) + 256)


def build(landmarks, recipe, source, excluded, *, backend, analysis, protected_boxes=()):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return None
    if backend != 'mediapipe':
        raise ValueError('Eye symmetry refuses template or placeholder analysis')
    _source(source)
    shape = tuple(source.shape[:2])
    retained = _retained(landmarks, analysis, shape, excluded)
    lm = pixels(retained, shape)
    boxes = _boxes(protected_boxes, shape)
    measured = _measure(lm)
    observed = {}
    for side in SIDES:
        side_evidence, *_ = evidence(lm, source, excluded, side)
        fact = side_evidence['size']
        if fact['reason'] is not None:
            raise ValueError('Eye symmetry needs both visible eyes; ' + side + ': ' + fact['reason'])
        observed[side] = int(fact['support_px'])
    reference, scales, shifts = _corrections(measured, recipe)
    # Even a measured already-symmetric identity requires the real installed ABI.
    if not native_available():
        raise RuntimeError('Eye symmetry requires the installed shared eye-shape Rust ABI')
    P, D, windows, source_eyes, target_eyes = [], [], [], [], []
    protected = [lm[list(NOSE_PROTECTION)], lm[list(LIPS)]]
    protected.extend(lm[list(upper + tuple(reversed(lower)))] for upper, lower in CHAINS.values())
    for side in SIDES:
        eye = measured['eyes'][side]
        points = eye['points']
        frame = np.r_[eye['outward'], measured['up'], eye['center'], points[16], eye['width'], eye['height']]
        expected = (points - eye['center']) * (scales[side] - 1.) + shifts[side] * measured['up']
        if np.any(np.any(expected != 0., axis=1) & np.all(points + expected == points, axis=1)):
            raise ValueError('Eye symmetry requested target is not representable at source precision')
        delta = native_controls(points, frame, scale=float(scales[side]), shift=float(shifts[side]))
        if (type(delta) is not np.ndarray or delta.dtype != np.float64
                or delta.shape != (21, 2) or not np.isfinite(delta).all()):
            raise ValueError('Eye symmetry native output violates its finite float64 21-point contract')
        motion = np.hypot(expected[:, 0], expected[:, 1])
        difference = delta - expected
        if np.any(np.hypot(difference[:, 0], difference[:, 1]) > np.where(motion > 0., motion * 1e-10, 0.)):
            raise ValueError('Eye symmetry native output did not realize the full requested correction')
        target = points + delta
        moving = np.any(delta != 0., axis=1)
        if np.any(moving & np.all(target == points, axis=1)):
            raise ValueError('Eye symmetry requested target is not representable at source precision')
        _guard_points(points, shape, boxes)
        _guard_points(target, shape, boxes)
        if np.any(moving):
            together = np.concatenate((points, target))
            center = together.mean(0)
            flat = float(np.max(np.linalg.norm(together - center, axis=1))) + eye['width'] * .04
            radius = flat + eye['width'] * .25
            low, high = center - radius, center + radius
            _guard_points(np.array([low, high]), shape, ())
            # Conservative complete support bounding boxes, not just endpoints
            # or the nominal lid ring, protect every retained foreign face.
            for normalized in boxes:
                box = np.asarray(normalized) * [shape[1] - 1, shape[0] - 1, shape[1] - 1, shape[0] - 1]
                if np.all(high >= box[:2] - 1.) and np.all(low <= box[2:] + 1.):
                    raise ValueError('Eye symmetry complete support touches another retained face')
            windows.append((center, flat, radius))
        else:
            # Size-reference/inactive source opening is protected continuously,
            # not merely by 21 zero pins. No whole reference support exclusion.
            protected.append(points[:16])
        P.extend(target); D.extend(delta)
        source_eyes.append(points); target_eyes.append(target)
    pins = lm[list(ANCHORS)]
    P.extend(pins); D.extend(np.zeros_like(pins))
    border = np.asarray(BORDER_ANCHORS) * [shape[1], shape[0]]
    P.extend(border); D.extend(np.zeros_like(border))
    requested_P, requested_D = np.asarray(P), np.asarray(D)
    tolerance = max(.02, min(shape) * 1e-5)
    for i in range(len(requested_P)):
        close = np.linalg.norm(requested_P[i + 1:] - requested_P[i], axis=1) < tolerance
        # Never average distinct moving requests, including tiny differences,
        # into a silent attenuation. Zero/zero duplicate pins are harmless.
        if np.any(close & np.any(requested_D[i + 1:] != requested_D[i], axis=1)):
            raise ValueError('Eye symmetry moving controls conflict with retained protection anchors')
    P, D, merged = dedupe_controls(requested_P, requested_D, tol=tolerance)
    common = {'requirement_id': REQUIREMENT_ID, 'reason': None, 'limitation': LIMITATION,
              'head_axis': 'forehead10_chin152_with_ordered_nose_bridge_consistency',
              'left_support_px': observed['left'], 'right_support_px': observed['right'],
              'native_abi': 'unchanged_eye_shape_v1', 'all_points_per_eye': 21}
    facts = {
        'horizontal': {**common, 'requested': recipe['horizontal'] != 0.,
            'applied': recipe['horizontal'] != 0., 'strength': recipe['horizontal'],
            'source_head_up_difference_px': measured['height_difference'],
            'left_head_up_translation_px': shifts['left'], 'right_head_up_translation_px': shifts['right'],
            'already_symmetric': measured['height_difference'] == 0.,
            'policy': 'bilateral_equal_opposite_translation_toward_head_relative_mean'},
        'size': {**common, 'requested': recipe['size'] != 0., 'applied': recipe['size'] != 0.,
            'strength': recipe['size'], 'reference': recipe['reference'], 'resolved_reference': reference,
            'reference_scope': 'size_only_horizontal_is_independent',
            'left_opening_area_px2': measured['eyes']['left']['area'],
            'right_opening_area_px2': measured['eyes']['right']['area'],
            'left_scale': scales['left'], 'right_scale': scales['right'],
            'already_symmetric': measured['eyes']['left']['area'] == measured['eyes']['right']['area'],
            'policy': 'isotropic_linear_strength_toward_sqrt_reference_to_target_lid_area_ratio'},
    }
    meta = {'controls': facts, 'merged': merged, 'windows': windows, 'landmarks': lm,
            'protected': protected, 'iris_only': [], 'protected_boxes': boxes,
            'source_eyes': source_eyes, 'target_eyes': target_eyes,
            'requested_P': requested_P, 'requested_D': requested_D}
    return EyeSymmetryField(P, D, meta, shape)
