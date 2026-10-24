# SPDX-License-Identifier: GPL-3.0-or-later
"""Original measured-lip dark-furrow support. AUTHORED / UNRUN.

Only existing, source-visible upper/lower vermilion surfaces are admitted. The
six-class model supplies known-occluder vetoes, NOT lip segmentation or complete
visibility. No lipstick review, face-skin assumption, replacement texture or
persisted support owner is borrowed. The canonical analysis owner authenticates
the source/model association of ``excluded``; no per-plane producer-grid proof
that the existing producer does not retain is invented here.
"""
import hashlib
import math
import numpy as np
from . import lip_texture_state as S, lip_texture_native as N, people_state as P
from .face_scope import _polygon_field
from .lip_makeup_geometry import INNER
from .ops.enhance import LIP_CHAIN_UPPER, LIP_CHAIN_LOWER

_FOOTPRINT = math.sqrt(.5)
_FIXED_BYTES = 16 * 1024**2
_MAX_WINDOW_PIXELS = 4_000_000
_LUMA = np.array([.2126, .7152, .0722], np.float32)
_INNER_UPPER = INNER[:11]
_INNER_LOWER = (INNER[0], *reversed(INNER[10:]))


def _poll(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('Original lip-texture preparation cancelled; no partial layer published')


def _boxes(protected_boxes):
    if type(protected_boxes) not in (tuple, list) or len(protected_boxes) > P.MAX_FACES:
        raise ValueError('Lip texture needs every retained same-source foreign face box')
    result = []
    for box in protected_boxes:
        if (type(box) not in (tuple, list) or len(box) != 4
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)
                or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1)):
            raise ValueError('Lip-texture foreign protection requires normalized source boxes')
        result.append(tuple(box))
    return result


def _geometry(landmarks, shape):
    """Two measured monotone surfaces, never a whole outer-mouth/teeth fill.

    Current-grid coordinates use the existing lip convention: normalized points
    times [width,height], with pixel centers at n+.5. The inner upper/lower
    chains may coincide for a genuinely closed mouth, but must each span the
    mouth in topology order. A full-width zigzag or collapsed point is refused.
    """
    h, w = shape
    points = landmarks[:, :2].astype(np.float64) * [w, h]
    width = float(np.linalg.norm(points[291]-points[61]))
    if width < 40:
        raise ValueError('Lip texture has insufficient measured source resolution')
    across = (points[291]-points[61])/width
    down = np.array([-across[1], across[0]], np.float64)
    if np.dot(points[17]-points[0], down) < 0:
        down = -down
    eye_widths = [float(np.linalg.norm(points[a]-points[b])) for a, b in ((33,133),(263,362))]
    halves = [float(np.linalg.norm(points[i]-points[0])) for i in (61,291)]
    if (min(eye_widths) < 8 or min(eye_widths) < .55*max(eye_widths)
            or min(halves) < .45*max(halves)):
        raise ValueError('Lip texture refuses strongly foreshortened measured anatomy')
    chains = [points[list(ids)] for ids in
              (LIP_CHAIN_UPPER, LIP_CHAIN_LOWER, _INNER_UPPER, _INNER_LOWER)]
    projected = []
    for chain in chains:
        u, v = chain@across, chain@down
        if np.any(np.diff(u) <= .001*width):
            raise ValueError('Lip texture requires ordered noncollapsed measured lip chains')
        projected.append((u, v))
    ou, ol, iu, il = projected
    if min(iu[0][-1]-iu[0][0], il[0][-1]-il[0][0]) < .55*width:
        raise ValueError('Lip texture refuses collapsed or shortened inner contours')
    # Inner corners must be genuinely inside the outer span. Piecewise-linear
    # order at the union of all knots proves complete segment containment, not
    # merely containment of vertices in a potentially concave outer polygon.
    left, right = float(iu[0][0]), float(iu[0][-1])
    if (left <= ou[0][0]+_FOOTPRINT or right >= ou[0][-1]-_FOOTPRINT
            or abs(left-il[0][0]) > 1e-6 or abs(right-il[0][-1]) > 1e-6):
        raise ValueError('Lip texture inner contour is not contained by measured outer corners')
    knots = np.unique(np.concatenate([u[(u >= left) & (u <= right)] for u, _ in projected]))
    rows = [np.interp(knots, u, v) for u, v in projected]
    if (np.any(rows[2] > rows[3]+1e-6) or np.any(rows[0] >= rows[2])
            or np.any(rows[3] >= rows[1])):
        raise ValueError('Lip texture refuses crossed, inverted or outward inner surfaces')
    outer_knots = np.unique(np.concatenate((ou[0], ol[0])))
    inner_knots = outer_knots[(outer_knots > ou[0][0]+1e-6) & (outer_knots < ou[0][-1]-1e-6)]
    if np.any(np.interp(inner_knots, ou[0], ou[1]) >= np.interp(inner_knots, ol[0], ol[1])):
        raise ValueError('Lip texture refuses crossed outer lip surfaces')
    # Original unvalidated scale policy. Actual surface thickness is checked
    # below through complete square-3r footprints on EACH measured surface;
    # never quietly reduce this requested scale to make a thin lip pass.
    radius = max(1, int(math.floor(width*.012)))
    if radius > 12:
        raise ValueError('Measured lip-texture radius exceeds native support; no scale fallback')
    polygons = {'upper': np.concatenate((chains[0], chains[2][::-1])),
                'lower': np.concatenate((chains[1], chains[3][::-1]))}
    extent = np.concatenate(chains)
    x, y = np.floor(extent.min(axis=0)-2).astype(int)
    x1, y1 = np.ceil(extent.max(axis=0)+2).astype(int)+1
    if min(x, y) < 1 or x1 > w-1 or y1 > h-1:
        raise ValueError('Lip texture refuses clipped measured lip support')
    rh, rw = int(y1-y), int(x1-x)
    if rh*rw > _MAX_WINDOW_PIXELS:
        raise ValueError('Lip-texture source window exceeds budget; no downsampling')
    return {'window': (int(y), int(x), rh, rw), 'polygons': polygons,
            'across': across, 'width': width, 'radius': radius,
            'left': left, 'right': right, 'shape': (h, w)}


def _full_support(coverage, radius):
    """Exact native square-3r permission, including each bilinear footprint.

    Unit coverage is geometric permission after binary evidence vetoes, NOT a
    claim of 100% semantic certainty. Strict full squares intentionally refuse
    narrow/low-resolution lips rather than bridge the seam, holes or another face.
    """
    margin = 3*radius
    h, w = coverage.shape
    out = np.zeros((h, w), bool)
    size = 2*margin+1
    if min(h, w) < size:
        return out
    invalid = coverage < np.float32(.999)
    integral = np.pad(invalid.astype(np.int64), ((1,0),(1,0))).cumsum(0).cumsum(1)
    count = (integral[size:,size:] - integral[:-size,size:]
             - integral[size:,:-size] + integral[:-size,:-size])
    out[margin:h-margin, margin:w-margin] = count == 0
    return out


def _observe(rgb, excluded, geometry, boxes, cancelled):
    """Observe this frozen ROI; no red-lip prior, makeup consent or skin gate."""
    _poll(cancelled)
    y, x, h, w = geometry['window']
    xx = np.arange(x, x+w, dtype=np.float64)[None, :]+.5
    yy = np.arange(y, y+h, dtype=np.float64)[:, None]+.5
    u = xx*geometry['across'][0]+yy*geometry['across'][1]
    feather = max(1., geometry['width']*.01)
    clearance = max(.8, geometry['width']*.008)
    corner = max(2., geometry['width']*.035)
    corner_weight = np.minimum(np.clip((u-geometry['left']-corner)/feather,0,1),
                               np.clip((geometry['right']-corner-u)/feather,0,1))
    protection = np.ones((h,w), np.float64)
    sh, sw = geometry['shape']
    for box in boxes:
        _poll(cancelled)
        left, top, right, bottom = np.asarray(box)*[sw,sh,sw,sh]
        pad = max(1., .015*max(right-left,bottom-top))
        dx = np.maximum(np.maximum(left-xx, xx-right), 0)
        dy = np.maximum(np.maximum(top-yy, yy-bottom), 0)
        protection *= np.clip((np.hypot(dx,dy)-_FOOTPRINT)/pad,0,1)
    linear = np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4)
    luma = linear@_LUMA
    # These are only vetoes for unobservable samples. In particular, darkness,
    # chromaticity or face-skin probability do not invent a lip label.
    # Match the native reliable() domain, not a weaker encoded-luma threshold:
    # otherwise a wholly unreliable image could masquerade as "no furrows".
    observed = ((excluded <= .1) & (luma >= .02)
                & np.all((rgb > .001) & (rgb < .985), axis=2))
    coverage = np.zeros((h,w), np.float32)
    sides = {}
    for side, polygon in geometry['polygons'].items():
        _poll(cancelled)
        inside, distance = _polygon_field(xx, yy, polygon)
        geometric = inside & (distance > _FOOTPRINT+clearance) & (corner_weight > 0)
        count = int(np.count_nonzero(geometric))
        visible = geometric & observed & (protection >= .999)
        if count < 24 or np.count_nonzero(visible) < max(24, .70*count):
            raise ValueError(side+' lip lacks sufficient unoccluded measured interior support')
        inward = np.clip((distance-_FOOTPRINT-clearance)/feather,0,1)
        part = np.ascontiguousarray(visible*inward*corner_weight, dtype=np.float32)
        eligible = _full_support(part, geometry['radius'])
        eligible_count = int(np.count_nonzero(eligible))
        if eligible_count < 4:
            raise ValueError(side+' lip has insufficient complete paired-flank footprints')
        if np.any((coverage > 0) & (part > 0)):
            raise ValueError('Measured upper/lower lip permission overlaps; no seam crossing')
        np.maximum(coverage,part,out=coverage)
        sides[side] = {'geometric_pixels': count, 'observed_pixels': int(np.count_nonzero(visible)),
                       'eligible_centers': eligible_count}
    coverage.setflags(write=False)
    return coverage, sides


def _validate_result(output, source, coverage, eligible):
    if (type(output) is not np.ndarray or output.dtype != np.float32 or output.shape != source.shape
            or not np.isfinite(output).all() or np.any((output < 0) | (output > 1))):
        raise ValueError('Lip-texture native output must be finite current-grid SDR float32 RGB')
    changed = np.any(output != source, axis=2)
    if np.any(changed & ((coverage <= 0) | ~eligible)):
        raise ValueError('Lip-texture native output changed a protected or unsupported footprint')
    if np.any(output < source-2e-7):
        raise ValueError('Lip-texture attenuation cannot darken the measured source')
    def linear(value):
        value = value.astype(np.float64)
        return np.where(value <= .04045, value/12.92, ((value+.055)/1.055)**2.4)
    before, after = linear(source), linear(output)
    for a,b in ((0,1),(0,2),(1,2)):
        if np.any(np.abs(after[...,a]*before[...,b]-after[...,b]*before[...,a]) > 2e-6):
            raise ValueError('Lip-texture native output changed source linear-RGB chromaticity')
    return changed


def prepare(face_ref, analysis, source, recipe, *, byte_budget, protected_boxes=(), cancelled=None):
    """One immutable source-local stage; export rebuilds then crops, never rescales.

    Caller supplies EVERY other retained same-source box, including disabled or
    unresolved faces, and the canonical exact analysis-owner row. The existing
    owner, not this pixel kernel, authenticates source/repair/document bytes.
    """
    recipe = S.check(recipe)
    if not S.active(recipe):
        return []
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    _poll(cancelled)
    ref = P.check_ref(face_ref)
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3
            or source.shape[2] != 3 or min(source.shape[:2]) < 1):
        raise ValueError('Lip texture needs current-source float32 working-sRGB RGB')
    h,w = source.shape[:2]
    baseline = h*w*32+_FIXED_BYTES
    if type(byte_budget) is not int or byte_budget < baseline:
        raise ValueError('Lip-texture source validation exceeds memory budget before allocation')
    if (type(analysis) is not dict
            or not {'face_ref','evidence','landmarks','excluded','skin'}.issubset(analysis)
            or analysis['face_ref'] != ref):
        raise ValueError('Lip texture needs the exact retained canonical analysis owner')
    evidence = P.check_evidence(analysis['evidence'])
    if evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe':
        raise ValueError('Lip texture needs actual measured face evidence, not template landmarks')
    P.digest(evidence['semantic_model_sha256'])
    landmarks = np.array(analysis['landmarks'], dtype='<f4', copy=True)
    if (landmarks.shape != (478,3) or not np.isfinite(landmarks).all()
            or np.any((landmarks[:,:2] < -1) | (landmarks[:,:2] > 2))
            or hashlib.sha256(np.ascontiguousarray(landmarks).tobytes()).hexdigest() != evidence['landmark_digest']):
        raise ValueError('Lip-texture geometry differs from its retained normalized478 digest')
    sw,sh = evidence['source_width'], evidence['source_height']
    if abs(w*sh-h*sw) > max(sw,sh):
        raise ValueError('Lip-texture current grid has a different source aspect ratio')
    boxes = _boxes(protected_boxes)
    geometry = _geometry(landmarks,(h,w))
    y,x,rh,rw = geometry['window']
    # Conservative simultaneous geometry, integral, result-validation and native
    # scratch admission, not a measured peak. No proxy/scale fallback is allowed.
    needed = baseline+rh*rw*384+N.memory_estimate((rh,rw))
    if needed > byte_budget:
        raise ValueError('Lip-texture full-source working set exceeds budget before allocation')
    if not np.isfinite(source).all() or np.any((source < 0) | (source > 1)):
        raise ValueError('Lip texture refuses nonfinite or HDR source instead of clipping')
    excluded = analysis['excluded']
    if (type(excluded) is not np.ndarray or excluded.dtype != np.float32 or excluded.shape != (h,w)
            or not np.isfinite(excluded).all() or np.any((excluded < 0) | (excluded > 1))):
        raise ValueError('Lip texture needs canonical current-grid known-occluder semantic evidence')
    frozen = np.array(source[y:y+rh,x:x+rw], dtype=np.float32, order='C', copy=True)
    veto = np.array(excluded[y:y+rh,x:x+rw], dtype=np.float32, order='C', copy=True)
    frozen.setflags(write=False); veto.setflags(write=False)
    coverage,sides = _observe(frozen,veto,geometry,boxes,cancelled)
    eligible = _full_support(coverage,geometry['radius'])
    if not N.available():
        raise RuntimeError('Lip-texture native kernel is unavailable; no Python effect fallback')
    _poll(cancelled)
    output = N.apply(frozen,coverage,recipe['amount'],across=tuple(geometry['across']),
                     radius=geometry['radius'],cancelled=cancelled or (lambda:False))
    changed = _validate_result(output,frozen,coverage,eligible)
    _poll(cancelled)
    delta = np.ascontiguousarray(output-frozen,dtype=np.float32)
    delta.setflags(write=False)
    count = int(np.count_nonzero(changed))
    facts = {'recipe':recipe,'face_ref':ref,'landmark_digest':evidence['landmark_digest'],
             'semantic_model_sha256':evidence['semantic_model_sha256'],
             'source_dimensions':[sw,sh],'render_dimensions':[w,h],
             'source_contract':'frozen-working-srgb-observed-lip-dark-furrows',
             'semantic_provenance':'existing-canonical-analysis-owner-known-occluder-veto',
             'support_method':'measured-separate-upper-lower-surfaces-binary-rgb-occluder-veto',
             'sides':sides,'radius':geometry['radius'],'measured_mouth_width':geometry['width'],
             'radius_policy':'max(1,floor(width*.012)); reject above12 or insufficient each-surface square3r support',
             'across':list(geometry['across']),'protected_face_boxes':len(boxes),
             'changed_pixels':count,'reason':None if count else 'no_eligible_dark_furrows',
             'native_solver':'rust-lip-texture-v1','review':'explicit-strength-and-canonical-before-after',
             'limitations':['not-lip-or-complete-occlusion-segmentation',
                            'unknown-skin-coloured-occluders-may-remain',
                            'dark-furrow-attenuation-only-not-flake-crack-or-lip-reconstruction',
                            'frontal-mild-yaw-sufficient-resolution-opaque-sdr-only',
                            'resampled-semantic-veto-is-not-new-full-resolution-inference']}
    from .people_effects import LocalEffect
    return [LocalEffect(ref,'lip_texture',geometry['window'],delta=delta,facts=facts)]
