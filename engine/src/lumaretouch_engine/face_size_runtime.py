# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-owned whole-face size, not a face-contour or slim-face alias.

AUTHORED / UNRUN. LNX-REF-PC-32466-C-728fc62cdd follows the whole-face
size direction documented at https://wiki.pixcakeai.com/guide/9405.html .
The original, deliberately bounded numeric policy is scale=1-.06*amount.
Measured oval, eyes, nose, mouth, brows and iris landmarks all share ONE exact
uniform scale in the flat core; none is pinned. The compact elliptical feather
also moves neighboring texture/background. This is not perfect background
isolation, full occlusion segmentation, 3-D reconstruction, AI generation or
commercial photographic parity. No external implementation has been copied.

Only the Rust kernel evaluates the pullback. Pixel evidence is scanned in
bounded tiles, and no image, dense map, analysis producer or image sampler is
retained here. Existing authenticated-analysis helpers retain their existing
full-frame validation behavior. Inverse sampling convention reference:
https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html .
"""
from dataclasses import dataclass

import numpy as np

from . import face_size_state as S
from . import face_contour_geometry as G
from .face_contour_runtime import require_analysis
from .face_size_native import evaluate as native_evaluate


MAX_POINTS = 65536
REQUIREMENT_ID = 'LNX-REF-PC-32466-C-728fc62cdd'
LIMITATION = ('2d_existing_texture_only; incomplete_boundary_and_occlusion_evidence; '
              'elliptical_halo_intentionally_transports_neighboring_background; '
              'prior_geometry_is_resized_not_identity_pinned; photographic_acceptance_unrun')


def _tiles(low, high):
    """Integer-center rectangles, with at most 65,536 points per temporary."""
    x0, y0 = map(int, low)
    x1, y1 = map(int, high)
    for y in range(y0, y1, 256):
        for x in range(x0, x1, 256):
            yield slice(y, min(y + 256, y1)), slice(x, min(x + 256, x1))


def _tile_points(ys, xs):
    yy, xx = np.mgrid[ys, xs]
    return np.column_stack((xx.ravel(), yy.ravel())).astype(np.float64)


def _source(source):
    if (type(source) is not np.ndarray or source.dtype not in (np.float32, np.float64)
            or source.ndim != 3 or source.shape[2] != 3 or min(source.shape[:2]) < 2):
        raise ValueError('Face size requires the actual same-frame source float RGB in [0,1]')
    h, w = source.shape[:2]
    for ys, xs in _tiles((0, 0), (w, h)):
        part = source[ys, xs]
        if not np.isfinite(part).all() or np.any((part < 0) | (part > 1)):
            raise ValueError('Face size source RGB is nonfinite or outside [0,1]')


def _segment_support(a, b, center, width, oval, source, skin, excluded):
    """Reuse contour's conservative inset strip, tiled only when it is large.

    The tiled path uses exactly the same strip, ratios and RGB thresholds as
    G._support_segment, not subsampling or a substitute visibility inference.
    """
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
    low = np.floor(poly.min(0) - 1).astype(int)
    high = np.ceil(poly.max(0) + 2).astype(int)
    h, w = source.shape[:2]
    if np.any(low < 1) or high[0] > w - 1 or high[1] > h - 1:
        return 'clipped_inner_skin_support', 0
    if int(high[0] - low[0]) * int(high[1] - low[1]) <= MAX_POINTS:
        return G._support_segment(a, b, center, width, oval, source, skin, excluded)
    strip_count = inside_count = visible_count = usable_count = 0
    total = total2 = 0.
    for ys, xs in _tiles(low, high):
        points = _tile_points(ys, xs)
        strip = G.polygon_inside(points, poly)
        inside = strip & G.polygon_inside(points, oval)
        visible = inside & (skin[ys, xs].ravel() >= .45) & (excluded[ys, xs].ravel() < .15)
        luma = source[ys, xs].reshape(-1, 3) @ np.array([.2126, .7152, .0722])
        usable = visible & (luma > .006) & (luma < .994)
        strip_count += int(np.count_nonzero(strip))
        inside_count += int(np.count_nonzero(inside))
        visible_count += int(np.count_nonzero(visible))
        usable_count += int(np.count_nonzero(usable))
        sample = luma[usable]
        total += float(np.sum(sample)); total2 += float(sample @ sample)
    if inside_count < max(12, .85 * strip_count):
        return 'insufficient_inner_oval_strip', inside_count
    if visible_count < max(12, .88 * inside_count):
        return 'occluded_or_missing_face_skin_support', visible_count
    variance = max(0., total2 / max(1, usable_count) - (total / max(1, usable_count))**2)
    if usable_count < .90 * visible_count or variance < .0025**2:
        return 'no_reliable_local_rgb_evidence', usable_count
    return None, usable_count


def _interior_support(lm, center, right, up, width, source, skin, excluded):
    """Require measured skin/RGB across all four interior quadrants.

    Feature interiors are exempt from the *skin-class* test, not from movement
    or the known-occluder veto. The inset excludes ambiguous perimeter pixels;
    all 36 actual boundary segments are separately checked above.
    """
    oval = lm[list(G.FACE_OVAL)]
    inset = center + .96 * (oval - center)
    low = np.floor(inset.min(0)).astype(int)
    high = np.ceil(inset.max(0)).astype(int) + 1
    counts = np.zeros(4, np.int64); observed = np.zeros(4, np.int64)
    usable_count = 0; total = total2 = 0.
    for ys, xs in _tiles(low, high):
        points = _tile_points(ys, xs)
        interior = G.polygon_inside(points, inset)
        veto = excluded[ys, xs].ravel()
        if np.any(interior & (veto >= .15)):
            raise ValueError('Face size refuses a known occluder inside the measured face')
        eligible = interior.copy()
        for ids in G.IDENTITY_POLYGONS:
            eligible &= ~G.polygon_inside(points, lm[list(ids)])
        local = points - center
        quadrants = ((local @ right >= 0).astype(np.int8)
                     + 2 * (local @ up >= 0).astype(np.int8))
        visible = eligible & (skin[ys, xs].ravel() >= .45)
        luma = source[ys, xs].reshape(-1, 3) @ np.array([.2126, .7152, .0722])
        usable = visible & (luma > .006) & (luma < .994)
        for quadrant in range(4):
            counts[quadrant] += np.count_nonzero(eligible & (quadrants == quadrant))
            observed[quadrant] += np.count_nonzero(usable & (quadrants == quadrant))
        sample = luma[usable]
        usable_count += len(sample)
        total += float(np.sum(sample)); total2 += float(sample @ sample)
    if np.any(counts < max(24, width * width * .002)) or np.any(observed < .85 * counts):
        raise ValueError('Face size lacks source face-skin/RGB evidence across the whole interior')
    variance = max(0., total2 / max(1, usable_count) - (total / max(1, usable_count))**2)
    if variance < .0025**2:
        raise ValueError('Face size lacks reliable interior RGB variation')
    return usable_count


def _measured_inside(lm, oval, width):
    """No outlying/template controls can silently enlarge the flat core."""
    inside = G.polygon_inside(lm, oval)
    distance = np.full(len(lm), np.inf)
    for a, b in zip(oval, np.roll(oval, -1, axis=0)):
        edge = b - a
        t = np.clip(((lm - a) @ edge) / float(edge @ edge), 0., 1.)
        distance = np.minimum(distance, np.linalg.norm(lm - a - t[:, None] * edge, axis=1))
    if np.any(~inside & (distance > max(1., width * .005))):
        raise ValueError('Face size landmarks extend outside their measured face oval')


def _immutable(value):
    a = np.asarray(value, dtype=np.float64)
    # An immutable bytes owner prevents re-enabling WRITEABLE on the public view.
    return np.frombuffer(a.tobytes(order='C'), dtype=np.float64).reshape(a.shape)


@dataclass(frozen=True, init=False)
class FaceSizeField:
    """Immutable compact native pullback, with no eye/lip/nose identity pins.

    The exact uniform-core promise applies to this operator before composition.
    A preceding face-geometry/contour edit is intentionally resized as part of the
    existing image by SizedFace, rather than held fixed or silently attenuated.
    The guarantee encloses retained source/scaled-target points, not arbitrarily
    relocated points from earlier edits; those can reach the smooth feather.
    """
    shape: tuple
    state: object
    source_landmarks: object
    target_landmarks: object
    _fact_items: tuple

    def __init__(self, parameters, landmarks, target, shape, facts):
        for label, value, required_shape in (('parameters', parameters, (11,)),
                ('source landmarks', landmarks, (478, 2)), ('target landmarks', target, (478, 2))):
            if (type(value) is not np.ndarray or value.dtype != np.float64
                    or value.shape != required_shape or not np.isfinite(value).all()):
                raise ValueError('Face size needs finite exact-shape float64 ' + label)
        object.__setattr__(self, 'shape', tuple(shape))
        object.__setattr__(self, 'state', _immutable(parameters))
        object.__setattr__(self, 'source_landmarks', _immutable(landmarks))
        object.__setattr__(self, 'target_landmarks', _immutable(target))
        object.__setattr__(self, '_fact_items', tuple(facts.items()))
        center, scale = self.state[:2], float(self.state[10])
        relative_coefficient = (scale - 1.) / scale
        for points in (self.source_landmarks, self.target_landmarks):
            expected = (points - center) * relative_coefficient
            actual = self.evaluate(points)
            motion = np.linalg.norm(expected, axis=1)
            error = np.linalg.norm(actual - expected, axis=1)
            if np.any(error > motion * 1e-8) or np.any(actual[motion == 0] != 0):
                raise ValueError('Face size native uniform core differs from the full requested scale')
        source_at_target = self.target_landmarks - self.evaluate(self.target_landmarks)
        epsilon = np.finfo(np.float64).eps * max(shape) * 16
        if not np.allclose(source_at_target, self.source_landmarks, rtol=0., atol=epsilon):
            raise ValueError('Face size target landmarks do not pull back to the exact measured source')

    @property
    def parameters(self):
        return self.state

    @property
    def facts(self):
        # Ordinary JSON-compatible facts do not expose mutable field storage.
        return {'face_size': dict(self._fact_items)}

    def evaluate(self, points):
        points = np.asarray(points, dtype=np.float64)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError('Face size evaluation needs finite Nx2 pixel coordinates')
        out = np.empty_like(points)
        for start in range(0, len(points), MAX_POINTS):
            q = points[start:start + MAX_POINTS]
            if not np.isfinite(q).all():
                raise ValueError('Face size evaluation needs finite Nx2 pixel coordinates')
            value = native_evaluate(q, self.state)
            if (type(value) is not np.ndarray or value.dtype != np.float64
                    or value.shape != q.shape or not np.isfinite(value).all()):
                raise ValueError('Face size native pullback violated its finite float64 output contract')
            out[start:start + len(q)] = value
        return out

    def resident_bytes(self):
        return self.state.nbytes + self.source_landmarks.nbytes + self.target_landmarks.nbytes + 2048


def build(landmarks, recipe, source, excluded, *, backend, analysis, protected_boxes=()):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return None
    if backend != 'mediapipe':
        raise ValueError('Face size refuses placeholder, template or unverified face geometry')
    _source(source)
    shape = source.shape[:2]
    skin = require_analysis(landmarks, analysis, shape, excluded)
    # Hash identity is canonical float32. Extra caller precision is not evidence.
    lm = G.pixels(np.asarray(analysis['landmarks'], dtype='<f4'), shape)
    right, up, _, width = G.frame(lm)
    oval = lm[list(G.FACE_OVAL)]
    _measured_inside(lm, oval, width)
    coordinates = np.column_stack((oval @ right, oval @ up))
    midpoint = (coordinates.min(0) + coordinates.max(0)) * .5
    center = right * midpoint[0] + up * midpoint[1]
    scale = S.scale_for_amount(recipe['amount'])
    if scale == 1.:
        raise ValueError('Face size nonzero amount is below representable geometry precision')
    target = center + scale * (lm - center)
    both = np.concatenate((lm, target)) - center
    local = np.column_stack((both @ right, both @ up))
    half = np.max(np.abs(local), axis=0)
    half *= float(np.max(np.linalg.norm(local / half, axis=1)))
    # Small measured padding, not a generic circular face template.
    half += max(2., width * .025)
    # A fixed 25% feather preserves the exact core, avoids needlessly rejecting
    # ordinary portrait framing, and still bounds the inverse radial derivative
    # above .33 at either full-scale endpoint. Its visual transition remains an
    # explicit UNRUN photographic QA gate; it is never cropped or gain-reduced.
    inner, outer = 1., 1.25
    radial_bound = 1. - abs((scale - 1.) / scale) * (1. + 1.875 * outer / (outer - inner))
    if radial_bound < .20:
        raise ValueError('Face size feather cannot admit the full requested inverse radial derivative')
    radius = outer * np.hypot(right * half[0], up * half[1])
    low, high = center - radius, center + radius
    h, w = shape
    if np.any(low < 1) or np.any(high > [w - 2, h - 2]):
        raise ValueError('Face size complete influence bounding box is clipped by the source frame')
    boxes = G._boxes(protected_boxes, shape)
    if any(np.all(high >= box[:2] - 1) and np.all(low <= box[2:] + 1) for box in boxes):
        raise ValueError('Face size complete influence bounding box touches another retained face')
    boundary_count = 0
    for a, b in zip(oval, np.roll(oval, -1, axis=0)):
        reason, count = _segment_support(a, b, center, width, oval, source, skin, excluded)
        if reason:
            raise ValueError('Face size full measured oval support refused: ' + reason)
        boundary_count += count
    interior_count = _interior_support(lm, center, right, up, width, source, skin, excluded)
    parameters = np.concatenate((center, right, up, half, [inner, outer, scale]))
    core_radius = np.linalg.norm(local / half, axis=1)
    if not np.isfinite(parameters).all() or np.any(core_radius >= inner):
        raise ValueError('Face size cannot enclose every measured source and target landmark in its uniform core')
    facts = {'control': 'face_size', 'requirement_id': REQUIREMENT_ID,
             'requested': True, 'applied': True, 'reason': None,
             'amount': recipe['amount'], 'scale': scale,
             'boundary_support_px': boundary_count, 'interior_support_px': interior_count,
             'uniform_core_landmarks': 478, 'minimum_inverse_radial_derivative_bound': radial_bound,
             'uniform_core_scope': 'retained_source_and_scaled_target_not_arbitrary_prior_edited_points',
             'method': 'native_uniform_core_elliptical_quintic_pullback',
             'evidence': 'full_measured_oval_strips_plus_four_quadrant_source_skin_rgb_and_known_occluder_veto',
             'limitation': LIMITATION}
    return FaceSizeField(parameters, lm, target, shape, facts)
