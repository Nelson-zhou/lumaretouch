# SPDX-License-Identifier: GPL-3.0-or-later
"""Measured original-brow contrast in one frozen source-owned LocalEffect.

The existing 478-point topology bounds an observed dark brow, not an invented
hairline, a new eyebrow, or clinical hair/occlusion segmentation. Independently
measured adjacent forehead strips provide the native solver's reference. No
makeup review, mask asset, cache, geometry warp or per-tile solve is introduced.
Authored source only; photographic quality and native integration are UNRUN.
"""
import hashlib
import math
import numpy as np
from . import brow_enhance_state as S, brow_enhance_native as N, people_state as P
from .brow_makeup_geometry import CHAINS
from .face_scope import FACE_OVAL, LIPS, _polygon_field
from .ops.enhance import EYE_RING_LEFT, EYE_RING_RIGHT
from .nose_shape_geometry import NOSE
from .skin_colour_support import check_analysis_fields

_LUMA = np.array([.2126, .7152, .0722], dtype=np.float32)
_FOOTPRINT = math.sqrt(.5)
_FIXED_BYTES = 16 * 1024 * 1024
_MAX_WINDOW_PIXELS = 4_000_000


def _poll(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('Original-brow preparation cancelled; no partial layer published')


def _hull(vertices):
    """Conservative envelope of measured nose topology, never an inferred nose."""
    points = sorted(set(map(tuple, np.asarray(vertices, np.float64))))
    if len(points) < 3:
        raise ValueError('Original-brow protection needs nondegenerate measured nose geometry')
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])
    lower = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    result = np.asarray(lower[:-1] + upper[:-1], np.float64)
    if len(result) < 3:
        raise ValueError('Original-brow protection needs nondegenerate measured nose geometry')
    return result


def _brow(points, side):
    upper_ids, lower_ids = CHAINS[side]
    upper, lower = points[list(upper_ids)], points[list(lower_ids)]
    middle = (upper + lower) * .5
    width = float(np.linalg.norm(middle[-1] - middle[0]))
    if width < 24:
        raise ValueError(side + ' original brow is too small for measured source support')
    axis = (middle[-1] - middle[0]) / width
    up = np.array([-axis[1], axis[0]])
    # Vertex 10 orients the measured face frame only. It is NOT a hairline or
    # evidence that any forehead pixel is skin, visible, uniform or unoccluded.
    if np.dot(up, points[10] - middle.mean(axis=0)) < 0:
        up = -up
    thickness = (upper - lower) @ up
    if (np.min(thickness) < 1.5 or np.max(thickness) > .32 * width
            or np.any(np.diff(middle @ axis) < .025 * width)
            or np.any(np.linalg.norm(upper-lower, axis=1) > .38 * width)):
        raise ValueError(side + ' original brow has degenerate or strongly foreshortened geometry')
    gap, depth = .04 * width, .09 * width
    near, far = upper + up * gap, upper + up * (gap + depth)
    polygon = np.concatenate((upper, lower[::-1]))
    reference = np.concatenate((near, far[::-1]))
    # Per-pixel signed distance to the upper chain divides the two independently
    # observed strip halves. No hairline position is generated or claimed.
    return {'side': side, 'polygon': polygon, 'reference': reference,
            'upper': upper, 'middle': middle, 'axis': axis, 'up': up,
            'width': width, 'thickness': thickness, 'gap': gap, 'depth': depth}


def _geometry(landmarks, shape, active_sides):
    h, w = shape
    points = landmarks[:, :2].astype(np.float64) * [w-1, h-1]
    brows = {side: _brow(points, side) for side in ('left', 'right')}
    widths = [brows[side]['width'] for side in ('left', 'right')]
    if min(widths) < .55 * max(widths):
        raise ValueError('Original-brow enhancement refuses strongly foreshortened bilateral geometry')
    eyes = (points[list(EYE_RING_LEFT)], points[list(EYE_RING_RIGHT)])
    eye_widths = [float(np.linalg.norm(points[a]-points[b])) for a, b in ((33, 133), (263, 362))]
    if min(eye_widths) < 12 or min(eye_widths) < .55 * max(eye_widths):
        raise ValueError('Original-brow enhancement requires sufficient measured eye anatomy')
    protection = (*eyes, points[list(LIPS)], _hull(points[list(NOSE)]))
    oval = points[list(FACE_OVAL)]
    prepared = []
    for side in active_sides:
        brow = brows[side]
        radius = int(math.ceil(float(np.max(brow['thickness'])) + brow['gap'] + brow['depth'] + 2))
        if not 2 <= radius <= 128:
            raise ValueError(side + ' measured original-brow radius exceeds native limits; no scale fallback')
        extent = np.concatenate((brow['polygon'], brow['reference']))
        x, y = np.floor(extent.min(axis=0) - 2).astype(int)
        x1, y1 = np.ceil(extent.max(axis=0) + 2).astype(int) + 1
        if min(x, y) < 1 or x1 > w-1 or y1 > h-1:
            raise ValueError(side + ' original brow or independent forehead reference is clipped')
        rh, rw = int(y1-y), int(x1-x)
        if rh * rw > _MAX_WINDOW_PIXELS:
            raise ValueError('Original-brow source window exceeds geometric budget; no downsampling')
        other = 'right' if side == 'left' else 'left'
        prepared.append({**brow, 'radius': radius, 'window': (int(y), int(x), rh, rw),
                         'oval': oval, 'protection': (*protection, brows[other]['polygon']),
                         'all_brows': (brows['left']['polygon'], brows['right']['polygon'])})
    return prepared


def _boxes(protected_boxes):
    if type(protected_boxes) not in (list, tuple) or len(protected_boxes) > P.MAX_FACES:
        raise ValueError('Original-brow neighbour protection exceeds retained face budget')
    boxes = []
    for box in protected_boxes:
        if (type(box) not in (list, tuple) or len(box) != 4
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)
                or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1)):
            raise ValueError('Original-brow neighbour protection needs retained source-normalized boxes')
        boxes.append(tuple(box))
    return boxes


def _boundary_weight(xx, yy, geometry, boxes, shape, cancelled):
    _poll(cancelled)
    inside, distance = _polygon_field(xx, yy, geometry['oval'])
    feather = max(1., .025 * geometry['width'])
    weight = np.where(inside, np.clip((distance-_FOOTPRINT)/feather, 0, 1), 0)
    for polygon in geometry['protection']:
        _poll(cancelled)
        inside, distance = _polygon_field(xx, yy, polygon)
        weight *= np.where(inside, 0, np.clip((distance-_FOOTPRINT)/feather, 0, 1))
    h, w = shape
    for box in boxes:
        _poll(cancelled)
        left, top, right, bottom = np.asarray(box) * [w, h, w, h]
        pad = max(1., .015 * max(right-left, bottom-top))
        halo = pad + _FOOTPRINT
        if (right+halo < xx[0, 0] or left-halo > xx[0, -1]
                or bottom+halo < yy[0, 0] or top-halo > yy[-1, 0]):
            continue
        dx = np.maximum(np.maximum(left-xx, xx-right), 0)
        dy = np.maximum(np.maximum(top-yy, yy-bottom), 0)
        weight *= np.clip((np.hypot(dx, dy)-_FOOTPRINT)/pad, 0, 1)
    return weight


def _strip_height(xx, yy, geometry):
    """Signed local normal distance from the measured piecewise upper chain."""
    best = np.full(np.broadcast_shapes(xx.shape, yy.shape), np.inf)
    height = np.zeros_like(best)
    for a, b in zip(geometry['upper'][:-1], geometry['upper'][1:]):
        vector = b-a
        length2 = float(vector @ vector)
        if length2 <= 1e-8:
            raise ValueError('Original-brow upper chain contains a degenerate segment')
        t = np.clip(((xx-a[0])*vector[0]+(yy-a[1])*vector[1])/length2, 0, 1)
        dx, dy = xx-a[0]-t*vector[0], yy-a[1]-t*vector[1]
        distance2 = dx*dx+dy*dy
        take = distance2 < best
        height[take] = (dx*geometry['up'][0]+dy*geometry['up'][1])[take]
        np.minimum(best, distance2, out=best)
    return height


def _observe(source, skin, excluded, geometry, boxes, cancelled):
    """RGB, semantic and geometry observations; never consume makeup consent."""
    _poll(cancelled)
    y, x, h, w = geometry['window']
    rgb = source[y:y+h, x:x+w]
    face_skin = skin[y:y+h, x:x+w]
    veto = excluded[y:y+h, x:x+w]
    xx = np.arange(x, x+w, dtype=np.float64)[None, :] + .5
    yy = np.arange(y, y+h, dtype=np.float64)[:, None] + .5
    inside, edge = _polygon_field(xx, yy, geometry['polygon'])
    reference_inside, _ = _polygon_field(xx, yy, geometry['reference'])
    protection = _boundary_weight(xx, yy, geometry, boxes, source.shape[:2], cancelled)
    reference_allowed = protection >= .95
    # Even if an unusual projected strip intersects either brow, those source
    # pixels are never allowed to masquerade as independent forehead reference.
    for polygon in geometry['all_brows']:
        brow_inside, brow_distance = _polygon_field(xx, yy, polygon)
        reference_allowed &= ~brow_inside & (brow_distance > _FOOTPRINT)
    luma = rgb @ _LUMA
    valid_rgb = (luma > .05) & (luma < .92) & np.all((rgb > .025) & (rgb < .98), axis=2)
    reliable = reference_inside & reference_allowed & (face_skin >= .75) & (veto <= .1) & valid_rgb
    u = ((xx-geometry['middle'][0, 0])*geometry['axis'][0]
         + (yy-geometry['middle'][0, 1])*geometry['axis'][1]) / geometry['width']
    strip_height = _strip_height(xx, yy, geometry)
    near_half = strip_height < geometry['gap'] + .5 * geometry['depth']
    target = np.zeros((h, w), np.float32)
    reference = np.zeros((h, w), np.float32)
    thirds = []
    medians, chromas = [], []
    feather = max(1., .025 * geometry['width'])
    geometric_target = inside & (protection >= .95) & (veto <= .1)
    # Eligibility is binary source evidence. A steep darkness-dependent opacity
    # would distort tonal ordering; the native log residual controls strength.
    # Its tonal-order property is conditional on fixed admitted coverage and
    # reference, NOT across these source-confidence or geometric boundaries.
    target_rgb = (luma > .008) & np.all(rgb < .98, axis=2)
    for third in range(3):
        _poll(cancelled)
        longitudinal = (u >= third/3) & (u < (third+1)/3)
        if third == 2:
            longitudinal |= (u >= 1) & (u < 1.02)
        if third == 0:
            longitudinal |= (u < 0) & (u > -.02)
        geometric_reference = reference_inside & longitudinal
        selected = reliable & longitudinal
        count, extent = int(np.count_nonzero(selected)), int(np.count_nonzero(geometric_reference))
        if extent < 8 or count < max(8, .80 * extent):
            raise ValueError(geometry['side'] + ' forehead third lacks independent visible skin/RGB support')
        values = luma[selected]
        median = float(np.median(values))
        noise = float(1.4826 * np.median(np.abs(values-median)))
        low, high = np.quantile(values, [.10, .90])
        if high-low > max(.035, .12*median) or noise > .025:
            raise ValueError(geometry['side'] + ' forehead reference is nonuniform, shadowed or noisy')
        near = selected & near_half
        far = selected & ~near_half
        if min(int(np.count_nonzero(near)), int(np.count_nonzero(far))) < 4:
            raise ValueError(geometry['side'] + ' forehead strip halves lack independent support')
        if abs(float(np.median(luma[near]))-float(np.median(luma[far]))) > max(.025, .08*median):
            raise ValueError(geometry['side'] + ' forehead strip has a shadow or illumination boundary')
        reference_chroma = rgb[selected] / values[:, None]
        chroma = np.median(reference_chroma, axis=0)
        if float(np.quantile(np.linalg.norm(reference_chroma-chroma, axis=1), .9)) > .10:
            raise ValueError(geometry['side'] + ' forehead reference contains inconsistent RGB colour')
        brow_region = inside & longitudinal
        visible = geometric_target & longitudinal
        brow_count = int(np.count_nonzero(brow_region))
        if brow_count < 8 or np.count_nonzero(visible) < .75*brow_count:
            raise ValueError(geometry['side'] + ' original brow is occluded or protected by another feature/face')
        dark = visible & target_rgb & (luma < median-max(.025, 3*noise))
        dark_count = int(np.count_nonzero(dark))
        if dark_count < max(6, .12*brow_count) or float(np.std(luma[visible])) < .006:
            raise ValueError(geometry['side'] + ' original brow has insufficient measured dark source contrast')
        feathered = np.clip((edge-_FOOTPRINT)/feather, 0, 1) * protection * (1-veto)
        target[dark] = feathered[dark].astype(np.float32)
        reference[selected] = (face_skin[selected]*(1-veto[selected])).astype(np.float32)
        if np.count_nonzero(target[longitudinal] > 0) < 4:
            raise ValueError(geometry['side'] + ' original brow has insufficient interior source pixels')
        medians.append(median)
        chromas.append(chroma)
        thirds.append({'third': third, 'reference_pixels': count, 'reference_geometric_pixels': extent,
                       'source_dark_pixels': dark_count, 'reference_median_luma': median,
                       'reference_noise_mad': noise})
    if max(medians)-min(medians) > max(.04, .12*float(np.mean(medians))):
        raise ValueError(geometry['side'] + ' forehead reference thirds cross an illumination or shadow boundary')
    if any(float(np.linalg.norm(a-b)) > .10 for a in chromas for b in chromas):
        raise ValueError(geometry['side'] + ' forehead reference thirds have inconsistent RGB colour')
    if np.any((target > 0) & (reference > 0)):
        raise ValueError('Original-brow target and independently measured reference overlap')
    target = np.ascontiguousarray(target, dtype=np.float32)
    reference = np.ascontiguousarray(reference, dtype=np.float32)
    target.setflags(write=False)
    reference.setflags(write=False)
    return target, reference, {'thirds': thirds, 'target_pixels': int(np.count_nonzero(target)),
        'reference_pixels': int(np.count_nonzero(reference)), 'radius': geometry['radius'],
        'measured_brow_width': geometry['width'], 'window': geometry['window']}


def _validate_result(output, source, target, amount):
    if (type(output) is not np.ndarray or output.dtype != np.float32 or output.shape != source.shape
            or not np.isfinite(output).all() or np.any((output < 0) | (output > 1))):
        raise ValueError('Original-brow native output must be finite SDR float32 RGB')
    if not np.array_equal(output[target == 0], source[target == 0]):
        raise ValueError('Original-brow native output changed protected source pixels')
    if ((amount > 0 and np.any(output > source + 2e-7))
            or (amount < 0 and np.any(output < source - 2e-7))):
        raise ValueError('Original-brow native output reversed the requested signed contrast direction')
    # The common gain is in LINEAR RGB. Encoded sRGB ratios are not preserved
    # by its transfer function and are not a valid chromaticity invariant.
    def linear(value):
        value = value.astype(np.float64)
        return np.where(value <= .04045, value/12.92, ((value+.055)/1.055)**2.4)
    source_linear, output_linear = linear(source), linear(output)
    for a, b in ((0, 1), (0, 2), (1, 2)):
        if np.any(np.abs(output_linear[..., a]*source_linear[..., b]
                         - output_linear[..., b]*source_linear[..., a]) > 2e-6):
            raise ValueError('Original-brow native output changed source linear RGB chromaticity')


def prepare(face_ref, analysis, source, recipe, *, byte_budget, protected_boxes=(), cancelled=None):
    """Prepare complete current-source fields once; export only crops this delta.

    The caller must pass EVERY other current same-source retained face box,
    including disabled/unresolved faces. No face-list position is an identity.
    Semantic planes are on the current render grid; retained normalized points,
    source evidence and original semantic producer dimensions stay canonical.
    """
    recipe = S.check(recipe)
    if not S.active(recipe):
        return []  # Neutral does not require model, support, native ABI or memory.
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be a callable')
    _poll(cancelled)
    ref = P.check_ref(face_ref)
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3
            or source.shape[2] != 3 or min(source.shape[:2]) < 1):
        raise ValueError('Original-brow enhancement requires current-source float32 working-sRGB RGB')
    h, w = source.shape[:2]
    # Before full-source finite scans or image-sized geometry allocations.
    baseline = h*w*32 + _FIXED_BYTES
    if type(byte_budget) is not int or byte_budget < baseline:
        raise ValueError('Original-brow source validation exceeds memory budget before allocation')
    if (type(analysis) is not dict
            or not {'face_ref', 'evidence', 'landmarks', 'excluded', 'skin'}.issubset(analysis)
            or analysis['face_ref'] != ref):
        raise ValueError('Original-brow enhancement requires the exact retained analysis owner')
    evidence = P.check_evidence(analysis['evidence'])
    if evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe':
        raise ValueError('Original-brow enhancement requires real retained measured face evidence')
    P.digest(evidence['semantic_model_sha256'])
    landmarks = np.asarray(analysis['landmarks'], dtype='<f4')
    if (landmarks.shape != (478, 3) or not np.isfinite(landmarks).all()
            or np.any((landmarks[:, :2] < -1) | (landmarks[:, :2] > 2))
            or hashlib.sha256(np.ascontiguousarray(landmarks).tobytes()).hexdigest() != evidence['landmark_digest']):
        raise ValueError('Original-brow geometry differs from the retained normalized 478-point digest')
    boxes = _boxes(protected_boxes)
    active_sides = [side for side in ('left', 'right') if recipe[side] != 0]
    geometry = _geometry(landmarks, (h, w), active_sides)
    y = min(g['window'][0] for g in geometry)
    x = min(g['window'][1] for g in geometry)
    y1 = max(g['window'][0]+g['window'][2] for g in geometry)
    x1 = max(g['window'][1]+g['window'][3] for g in geometry)
    # All active sides are admitted before rasterization or any native solve.
    # Include simultaneous geometry/observation fields, the merged output and
    # sequential native scratch. This is a conservative bound, not peak proof.
    native_bytes = [N.memory_estimate(g['window'][2:]) for g in geometry]
    reserved = baseline + (y1-y)*(x1-x)*24 + sum(g['window'][2]*g['window'][3]*320 for g in geometry)
    if reserved + max(native_bytes) > byte_budget:
        raise ValueError('Original-brow geometry and native windows exceed memory budget before allocation')
    if not np.isfinite(source).all() or np.any((source < 0) | (source > 1)):
        raise ValueError('Original-brow enhancement refuses nonfinite or HDR source; no clipping')
    observation = check_analysis_fields(analysis, (h, w))
    skin, excluded = analysis.get('face_skin'), analysis['excluded']
    if observation is None:
        raise ValueError('Original-brow forehead reference needs actual face-skin observation, not merged skin')
    for plane in (skin, excluded):
        if (type(plane) is not np.ndarray or plane.dtype != np.float32 or plane.shape != (h, w)
                or not np.isfinite(plane).all() or np.any((plane < 0) | (plane > 1))):
            raise ValueError('Original-brow source support needs current-grid skin and known-occluder evidence')
    if not N.available():
        raise RuntimeError('Original-brow native kernel is unavailable; no Python effect fallback')
    observed = []
    for g in geometry:
        target, reference, facts = _observe(source, skin, excluded, g, boxes, cancelled)
        observed.append((g, target, reference, facts))
    _poll(cancelled)
    merged = np.zeros((y1-y, x1-x, 3), np.float32)
    occupied = np.zeros(merged.shape[:2], bool)
    sides = {side: {'requested': recipe[side], 'reason': 'disabled', 'changed_pixels': 0}
             for side in ('left', 'right')}
    for g, target, reference, facts in observed:
        _poll(cancelled)
        gy, gx, gh, gw = g['window']
        frozen = np.array(source[gy:gy+gh, gx:gx+gw], dtype=np.float32, order='C', copy=True)
        frozen.setflags(write=False)
        output = N.apply(frozen, target, recipe[g['side']], reference_coverage=reference,
                         radius=g['radius'], cancelled=cancelled or (lambda: False))
        _validate_result(output, frozen, target, recipe[g['side']])
        delta = np.ascontiguousarray(output-frozen, dtype=np.float32)
        changed = np.any(delta != 0, axis=2)
        used = occupied[gy-y:gy-y+gh, gx-x:gx-x+gw]
        if np.any(used & changed):
            raise ValueError('Original-brow side fields overlap; no partial or repeated correction')
        merged[gy-y:gy-y+gh, gx-x:gx-x+gw][changed] = delta[changed]
        used[changed] = True
        count = int(np.count_nonzero(changed))
        sides[g['side']] = {**facts, 'requested': recipe[g['side']], 'changed_pixels': count,
                           'reason': None if count else 'no_measurable_change'}
    _poll(cancelled)
    if not np.isfinite(merged).all():
        raise ValueError('Original-brow merged source contribution is nonfinite')
    merged.setflags(write=False)
    from .people_effects import LocalEffect
    facts = {'recipe': recipe, 'face_ref': ref, 'landmark_digest': evidence['landmark_digest'],
             'semantic_model_sha256': evidence['semantic_model_sha256'], 'sides': sides,
             'source_dimensions': [evidence['source_width'], evidence['source_height']],
             'render_dimensions': [w, h], 'forehead_observation': observation,
             'changed_pixels': int(np.count_nonzero(occupied)), 'native_solver': 'rust-brow-enhance-v1',
             'source_contract': 'frozen-working-srgb-original-dark-brow-relative-to-independent-forehead',
             'review': 'explicit-strength-selection-and-existing-canonical-preview',
             'limitations': ['conservative-dark-source-evidence-not-complete-brow-or-occlusion-segmentation',
                             'no-invented-hairline-new-brow-dye-or-geometry',
                             'negative-strength-reduces-contrast-not-full-hair-or-makeup-removal'],
             'protected_face_boxes': len(boxes)}
    return [LocalEffect(ref, 'brow_enhance', (y, x, y1-y, x1-x), delta=merged, facts=facts)]
