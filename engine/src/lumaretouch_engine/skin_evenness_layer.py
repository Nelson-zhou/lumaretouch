# SPDX-License-Identifier: GPL-3.0-or-later
"""Original source-owned facial colour-evenness support. AUTHORED / UNRUN.

This is an independent low-frequency log-chroma operation, not the old broad
skin recipe, skin blur, exposure, a defect classifier or a healthy-skin target.
The measured face's own usable source samples determine its reference. Existing
face-skin semantics and retained anatomy are intersected, never extended to body
skin or another person. Natural pigmentation, lighting and makeup are ambiguous;
explicit strength and the canonical before/after are the review mechanism.
"""
import hashlib
import math

import numpy as np

from . import people_state as P
from . import skin_evenness_native as N, skin_evenness_state as S
from .face_scope import FACE_OVAL, _polygon_field, selected_face_skin
from .skin_colour_support import check_analysis_fields

_FIXED_BYTES = 16 * 1024**2
_HOST_BYTES_PER_PIXEL = 32
_WINDOW_BYTES_PER_PIXEL = 256
_FOOTPRINT = math.sqrt(.5)
_REFERENCE_WEIGHT = .75
_MIN_REFERENCE_SAMPLES = 64
_LUMA = np.array([.2126, .7152, .0722], np.float64)


def _poll(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('Skin evenness cancelled; no partial layer published')


def _boxes(protected_boxes):
    """Only protection, never face ownership inferred from a rectangle."""
    if type(protected_boxes) not in (tuple, list) or len(protected_boxes) > P.MAX_FACES:
        raise ValueError('Skin evenness needs all retained same-source foreign face boxes')
    result = []
    for box in protected_boxes:
        if (type(box) not in (tuple, list) or len(box) != 4
                or any(type(v) not in (int, float) or not 0 <= v <= 1
                       or not math.isfinite(v) for v in box)
                or not (box[0] < box[2] and box[1] < box[3])):
            raise ValueError('Skin-evenness foreign protection needs normalized source boxes')
        result.append(tuple(box))
    return result


def _geometry(landmarks, shape):
    """Actual current-source pixel scale, not producer/proxy/evidence dimensions.

    Match selected_face_skin's normalized coordinates times [width,height] and
    n+.5 pixel centers. Unsupported scales refuse, never clamp or downsample.
    """
    h, w = shape
    oval = landmarks[list(FACE_OVAL), :2].astype(np.float64) * [w, h]
    width, height = np.ptp(oval, axis=0)
    radius = int(math.ceil(.08 * min(width, height)))
    if not 4 <= radius <= 256:
        raise ValueError('Measured skin-evenness radius is outside 4..256; no scale fallback')
    # ALL positive support is inside the measured oval. Retain a real source
    # halo beyond it for the two-pass guided dependency; never pad a crop or
    # recompute references on render tiles. Clip only at actual image edges.
    halo = 2*radius+1
    x0, y0 = np.maximum(np.floor(oval.min(axis=0)).astype(int)-halo, 0)
    x1, y1 = np.minimum(np.ceil(oval.max(axis=0)).astype(int)+1+halo, [w, h])
    if x1 <= x0 or y1 <= y0:
        raise ValueError('Skin evenness has no measured source window')
    window = (int(y0), int(x0), int(y1-y0), int(x1-x0))
    return oval, radius, {'width': float(width), 'height': float(height)}, window


def _protect(support, oval, boxes, cancelled):
    """Protect the whole outer-boundary pixel footprint and every foreign box.

    selected_face_skin already excludes eye/brow/lip interiors with outward
    feature feathering. Its oval is additionally inset by half a pixel diagonal
    here so a boundary-straddling pixel cannot supply or receive correction.
    """
    h, w = support.shape
    x0, y0 = np.maximum(np.floor(oval.min(axis=0)).astype(int), 0)
    x1, y1 = np.minimum(np.ceil(oval.max(axis=0)).astype(int)+1, [w, h])
    if x1 <= x0 or y1 <= y0:
        raise ValueError('Skin evenness has no visible measured face interior')
    xx = np.arange(x0, x1, dtype=np.float64)[None, :] + .5
    yy = np.arange(y0, y1, dtype=np.float64)[:, None] + .5
    interior, distance = _polygon_field(xx, yy, oval)
    feather = max(1., .015 * float(np.max(np.ptp(oval, axis=0))))
    support[y0:y1, x0:x1] *= interior * np.clip((distance-_FOOTPRINT)/feather, 0, 1)
    for box in boxes:
        _poll(cancelled)
        left, top, right, bottom = np.asarray(box, dtype=np.float64) * [w, h, w, h]
        feather = max(1., .015 * max(right-left, bottom-top))
        pad = feather + _FOOTPRINT + 1
        # A large foreign box must not allocate photograph-sized scratch when
        # this face occupies only a small admitted ROI. Outside this oval the
        # support is already zero, so intersect before any coordinate arrays.
        bx0, by0 = max(x0, int(math.floor(left-pad))), max(y0, int(math.floor(top-pad)))
        bx1, by1 = min(x1, int(math.ceil(right+pad))), min(y1, int(math.ceil(bottom+pad)))
        if bx1 <= bx0 or by1 <= by0 or not np.any(support[by0:by1, bx0:bx1] > 0):
            continue
        xx = np.arange(bx0, bx1, dtype=np.float64)[None, :] + .5
        yy = np.arange(by0, by1, dtype=np.float64)[:, None] + .5
        dx = np.maximum(np.maximum(left-xx, xx-right), 0)
        dy = np.maximum(np.maximum(top-yy, yy-bottom), 0)
        support[by0:by1, bx0:bx1] *= np.clip((np.hypot(dx, dy)-_FOOTPRINT)/feather, 0, 1)


def _reference_admission(source, coverage):
    """Photometric admission only, not a second reference/neighbourhood solver.

    Match native source reliability exactly: linear-light luminance and minimum
    channel floors, highlight and encoded clipping guards. At least 64 samples
    must have coverage*reliability >=.75. This is an observability heuristic, not
    skin-tone classification or makeup detection; native rechecks independently
    and owns the sole robust-reference and neighbourhood calculation.
    """
    rgb = source.astype(np.float64)
    linear = np.where(rgb <= .04045, rgb/12.92, ((rgb+.055)/1.055)**2.4)
    y = linear @ _LUMA
    def smooth(low, high, value):
        t = np.clip((value-low)/(high-low), 0., 1.)
        return t*t*(3.-2.*t)
    reliability = (smooth(.01, .04, y) * (1.-smooth(.70, .90, y))
                   * smooth(.002, .008, linear.min(axis=2))
                   * (1.-smooth(.95, .995, rgb.max(axis=2))))
    count = int(np.count_nonzero(coverage * reliability >= _REFERENCE_WEIGHT))
    if count < _MIN_REFERENCE_SAMPLES:
        raise ValueError('Skin evenness lacks 64 reliable target-owned source reference samples')
    return count, reliability > 0


def _validate_shift(shift, coverage, observable):
    if (type(shift) is not np.ndarray or shift.dtype != np.float32
            or shift.shape != (*coverage.shape, 2) or not np.isfinite(shift).all()):
        raise ValueError('Skin evenness needs finite current-source float32 HWC2 log-chroma shift')
    changed = np.any(shift != 0, axis=2)
    if np.any(changed & ((coverage <= 0) | ~observable)):
        raise ValueError('Skin-evenness native shift changed protected or unobservable source pixels')
    # Euclidean norm, not merely independent channel clamps. Small tolerance is
    # for float32 storage at the native bound, not permission to clip bad output.
    norm2 = np.sum(shift.astype(np.float64)**2, axis=2)
    if np.any(norm2 > (N.MAX_SHIFT+1e-7)**2):
        raise ValueError('Skin-evenness native log-chroma shift exceeds its vector bound')
    return changed


def prepare(face_ref, analysis, source, recipe, *, byte_budget, protected_boxes=(), cancelled=None):
    """Prepare one immutable HWC2 exact source-window field for pointwise use.

    The canonical render owner authenticates exact source/repair bytes, retains
    the matching analysis row, and supplies EVERY other retained same-source
    box, including disabled and unresolved faces. This layer validates that row
    and digest; array contents alone cannot authenticate source ownership.

    Native prepare sees every own-face source sample and a true 2*radius+1 halo
    exactly once. Native apply later receives CURRENT stage RGB and this field,
    preserving that stage's luminance. No source-derived RGB delta, per-tile
    reference recomputation, body consent, merged-skin fallback or promoted
    preview effect is accepted.
    """
    recipe = S.check(recipe)
    if not S.active(recipe):
        return []
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    _poll(cancelled)
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3
            or source.shape[2] != 3 or min(source.shape[:2]) < 1):
        raise ValueError('Skin evenness needs current-source float32 working-sRGB RGB')
    h, w = source.shape[:2]
    # Full-grid admission precedes source-sized validity arrays and anatomy.
    # After small retained-geometry validation, window admission independently
    # precedes all native/source-window allocation. This is conservative, not a
    # measured memory/latency guarantee or permission for proxy fallback.
    baseline = h*w*_HOST_BYTES_PER_PIXEL + _FIXED_BYTES
    if type(byte_budget) is not int or byte_budget < baseline:
        raise ValueError('Skin-evenness source validation exceeds memory budget before allocation')
    ref = P.check_ref(face_ref)
    if (type(analysis) is not dict
            or not {'face_ref', 'evidence', 'landmarks', 'excluded'}.issubset(analysis)
            or analysis['face_ref'] != ref):
        raise ValueError('Skin evenness needs the exact retained canonical analysis owner')
    evidence = P.check_evidence(analysis['evidence'])
    if evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe':
        raise ValueError('Skin evenness needs actual measured face evidence, not template landmarks')
    P.digest(evidence['semantic_model_sha256'])
    landmarks = np.array(analysis['landmarks'], dtype='<f4', order='C', copy=True)
    if (landmarks.shape != (478, 3) or not np.isfinite(landmarks).all()
            or np.any((landmarks[:, :2] < -1) | (landmarks[:, :2] > 2))
            or hashlib.sha256(landmarks.tobytes()).hexdigest() != evidence['landmark_digest']):
        raise ValueError('Skin-evenness anatomy differs from its retained normalized478 digest')
    sw, sh = evidence['source_width'], evidence['source_height']
    if abs(w*sh-h*sw) > max(sw, sh):
        raise ValueError('Skin-evenness current grid has a different source aspect ratio')
    boxes = _boxes(protected_boxes)
    oval, radius, span, window = _geometry(landmarks, (h, w))
    y, x, rh, rw = window
    if baseline + rh*rw*_WINDOW_BYTES_PER_PIXEL + N.memory_estimate((rh, rw)) > byte_budget:
        raise ValueError('Skin-evenness source-window working set exceeds memory budget before allocation')
    observation = check_analysis_fields(analysis, (h, w))
    if observation is None:
        raise ValueError('Skin evenness requires actual face_skin and face_skin_observation; no merged skin fallback')
    excluded = analysis['excluded']
    if (type(excluded) is not np.ndarray or excluded.dtype != np.float32 or excluded.shape != (h, w)
            or not np.isfinite(excluded).all() or np.any((excluded < 0) | (excluded > 1))):
        raise ValueError('Skin evenness needs canonical current-grid known-occluder exclusion evidence')
    if not np.isfinite(source).all() or np.any((source < 0) | (source > 1)):
        raise ValueError('Skin evenness refuses nonfinite or HDR source instead of clipping')
    _poll(cancelled)
    frozen = np.array(source[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
    frozen.setflags(write=False)
    # Only the named, validated face-skin class enters this anatomical selector.
    # Known occluders veto both source reference samples and correction targets.
    coverage = selected_face_skin(analysis['face_skin'], landmarks)
    coverage[excluded > .1] = 0
    _protect(coverage, oval, boxes, cancelled)
    coverage = np.array(coverage[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
    _poll(cancelled)
    reference_samples, observable = _reference_admission(frozen, coverage)
    coverage.setflags(write=False)
    if not N.available():
        raise RuntimeError('Skin-evenness native kernel is unavailable; no Python effect fallback')
    _poll(cancelled)
    shift = N.prepare(frozen, coverage, recipe['amount'], radius=radius,
                      cancelled=cancelled or (lambda: False))
    _poll(cancelled)
    changed = _validate_shift(shift, coverage, observable)
    _poll(cancelled)
    # The sole reference solve retained all own-face samples and genuine source
    # dependencies. Later tile cropping is valid; enlarging this field is not.
    field = np.array(shift, dtype=np.float32, order='C', copy=True)
    field.setflags(write=False)
    count = int(np.count_nonzero(changed))
    facts = {
        'operation_id': S.OP, 'recipe': recipe, 'face_ref': ref,
        'landmark_digest': evidence['landmark_digest'],
        'semantic_model_sha256': evidence['semantic_model_sha256'],
        'source_dimensions': [sw, sh], 'render_dimensions': [w, h],
        'source_window': list(window), 'source_halo': 2*radius+1,
        'face_skin_observation': observation,
        'scope': 'selected-measured-face-only', 'body_extension': {'enabled': False},
        'source_contract': 'immutable-effective-source-working-srgb-sdr',
        'support_method': 'actual-face-skin-intersect-measured-anatomy-known-occluder-and-foreign-box-veto',
        'reference_method': 'own-source-robust-log-chroma-reference',
        'reference_samples': reference_samples,
        'radius': radius, 'measured_face_span': span,
        'radius_policy': 'ceil(.08*min(current-source-oval-width,height)); reject outside4..256',
        'protected_face_boxes': len(boxes), 'changed_pixels': count,
        'field_contract': 'readonly-current-source-HWC2-log-chroma-shift',
        'application': 'pointwise-current-stage-linear-luminance-preserving',
        'reason': None if count else 'no-source-chroma-correction',
        'native_solver': 'rust-skin-evenness-v1',
        'review': 'explicit-strength-and-canonical-before-after',
        'limitations': [
            'original-low-frequency-colour-correction-not-ai-defect-classification',
            'not-skin-blur-exposure-or-lighting-material-separation',
            'natural-colour-lighting-pigment-and-makeup-remain-ambiguous',
            'no-invented-healthy-skin-target-or-automatic-makeup-protection',
            'no-body-or-cross-person-colour-matching',
            'resampled-semantic-observation-is-not-new-full-resolution-inference',
            'unknown-occlusion-and-model-anatomy-errors-require-before-after-review',
        ],
    }
    from .people_effects import LocalEffect
    return [LocalEffect(ref, 'skin_evenness', window, chroma_shift=field, facts=facts)]
