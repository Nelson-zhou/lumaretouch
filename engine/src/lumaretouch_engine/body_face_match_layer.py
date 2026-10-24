# SPDX-License-Identifier: GPL-3.0-or-later
"""Reviewed body-to-own-effective-source-stage-face colour matching. AUTHORED / UNRUN.

LNX-REF-PC-32465-C-d8b09012a9, guide 32465 lines 217–219. This separate
operation compares actual selected-face and reviewed same-person body samples
from ONE immutable effective source. It neither copies face RGB nor matches a
later corrected face, changes brightness, or claims a learned AI correction.
The existing current-stage compositor applies a bounded HWC2 chroma field while
preserving that stage's linear luminance. No body/face support is transferable.
"""
import hashlib
from copy import deepcopy

import numpy as np

from . import people_state as P
from . import skin_colour_body_support as SUPPORT
from . import skin_evenness_layer as FACE, body_skin_evenness_layer as BODY
from . import body_face_match_native as N, body_face_match_state as S

FAMILY = 'body_face_match'
_FIXED_BYTES = 64 * 1024**2
_HOST_BYTES_PER_PIXEL = 96
_RASTER_FIXED_BYTES = 32 * 1024**2
_RASTER_BYTES_PER_PIXEL = 24
_WINDOW_BYTES_PER_PIXEL = 256


def _poll(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('Body/face matching cancelled; no partial layer published')


def _source(source):
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3
            or source.shape[2] != 3 or min(source.shape[:2]) < 2):
        raise ValueError('Body/face matching needs current-source float32 working-sRGB RGB')
    return source.shape[:2]


def _baseline(shape):
    return shape[0]*shape[1]*_HOST_BYTES_PER_PIXEL + _FIXED_BYTES


def _window(coverage):
    """Reference storage only; face robust samples have no guided dependency."""
    rows = np.flatnonzero(np.any(coverage > 0, axis=1))
    columns = np.flatnonzero(np.any(coverage > 0, axis=0))
    if not len(rows) or not len(columns):
        raise ValueError('Body/face matching has no actual own-face reference support')
    result = (int(rows[0]), int(columns[0]), int(rows[-1]-rows[0]+1), int(columns[-1]-columns[0]+1))
    if min(result[2:]) < 2:
        raise ValueError('Body/face own-face reference has no reliable two-dimensional source region')
    return result


def reference_support(ref, analysis, source, *, people_state, byte_budget, cancelled=None):
    """Actual own-face-only full-source support and bounded review disclosure.

    The canonical caller authenticates source bytes and analysis. This helper
    additionally pins the selected retained FaceRef, actual face_skin observation
    and verified 478-point digest, excluding known occluders and every foreign
    retained same-source face (including disabled/unresolved faces). It is used
    unchanged by the source review overlay and the single native preparation.
    It performs admission only; the sole robust target solve remains in Rust.
    """
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    _poll(cancelled)
    h, w = _source(source); baseline = _baseline((h, w))
    if type(byte_budget) is not int or byte_budget < baseline:
        raise ValueError('Body/face reference exceeds memory budget before allocation')
    ref = P.check_ref(ref); state = P.check(people_state)
    face = state['faces'].get(ref['face_instance_id'])
    if (face is None or P.face_ref(face) != ref or not face['enabled']
            or type(analysis) is not dict or analysis.get('face_ref') != ref
            or analysis.get('evidence') != face['evidence']):
        raise ValueError('Body/face reference needs the exact enabled selected retained face')
    evidence = P.check_evidence(analysis['evidence'])
    if evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe':
        raise ValueError('Body/face reference requires actual verified face evidence, not template anatomy')
    P.digest(evidence['semantic_model_sha256'])
    landmarks = np.array(analysis.get('landmarks'), dtype='<f4', order='C', copy=True)
    if (landmarks.shape != (478, 3) or not np.isfinite(landmarks).all()
            or np.any((landmarks[:, :2] < -1) | (landmarks[:, :2] > 2))
            or hashlib.sha256(landmarks.tobytes()).hexdigest() != evidence['landmark_digest']):
        raise ValueError('Body/face reference anatomy differs from its verified normalized478 digest')
    sw, sh = evidence['source_width'], evidence['source_height']
    if abs(w*sh-h*sw) > max(sw, sh):
        raise ValueError('Body/face reference has a different current-source aspect ratio')
    # The face supplies only robust reference samples, not guided correction;
    # unlike the body it needs no arbitrary face-radius requirement or padding.
    oval = landmarks[list(FACE.FACE_OVAL), :2].astype(np.float64) * [w, h]
    low = np.maximum(np.floor(oval.min(axis=0)).astype(int), 0)
    high = np.minimum(np.ceil(oval.max(axis=0)).astype(int)+1, [w, h])
    if np.any(high <= low):
        raise ValueError('Body/face reference has no measured source face interior')
    extent = int(np.prod(high-low))
    if baseline + extent*_WINDOW_BYTES_PER_PIXEL > byte_budget:
        raise ValueError('Body/face reference anatomy exceeds memory budget before allocation')
    observation = FACE.check_analysis_fields(analysis, (h, w))
    if observation is None:
        raise ValueError('Body/face reference requires actual face_skin observation; no merged/donor fallback')
    excluded = analysis.get('excluded')
    if (type(excluded) is not np.ndarray or excluded.dtype != np.float32 or excluded.shape != (h, w)
            or not np.isfinite(excluded).all() or np.any((excluded < 0) | (excluded > 1))):
        raise ValueError('Body/face reference needs actual finite known-occluder evidence')
    if not np.isfinite(source).all() or np.any((source < 0) | (source > 1)):
        raise ValueError('Body/face matching refuses nonfinite or HDR source instead of clipping')
    boxes = FACE._boxes([item['box'] for item in state['faces'].values()
                         if item['asset_sha256'] == ref['asset_sha256'] and P.face_ref(item) != ref])
    _poll(cancelled)
    coverage = FACE.selected_face_skin(analysis['face_skin'], landmarks)
    coverage[excluded > .1] = 0
    FACE._protect(coverage, oval, boxes, cancelled)
    window = _window(coverage); y, x, rh, rw = window
    _poll(cancelled)
    samples, _ = FACE._reference_admission(source[y:y+rh, x:x+rw], coverage[y:y+rh, x:x+rw])
    coverage.setflags(write=False)
    facts = {'face_ref': ref, 'source': {'sha256': ref['asset_sha256'], 'width': sw, 'height': sh},
        'face_skin_observation': observation, 'scope': 'selected-own-face-effective-source-reference',
        'reference_method': 'effective-source-stage-own-face-robust-log-chroma',
        'source_window': list(window), 'support_pixels': int(np.count_nonzero(coverage > 0)),
        'reference_samples': samples, 'protected_face_boxes': len(boxes),
        'runtime_quality_accepted': False}
    return coverage, facts


def prepare(ref, analysis, source, recipe, *, people_state, body_assets, body_bank,
            byte_budget, cancelled=None):
    """Prepare ONE body HWC2 field from actual body/own-face source ROIs.

    Body geometry is the current retained visible/present shoulder/hip scale.
    Its full admitted region receives a true 2r+1 source halo, never per-tile
    solves. Both crops come from this same immutable effective-source array,
    not later stage pixels, another reference asset, or promoted preview bytes.
    Aggregate admission includes both ROIs and the combined native estimator.
    """
    recipe = S.check(recipe)
    if not S.active(recipe):
        return []
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    _poll(cancelled)
    h, w = _source(source); baseline = _baseline((h, w))
    raster_bytes = h*w*_RASTER_BYTES_PER_PIXEL + _RASTER_FIXED_BYTES
    if type(byte_budget) is not int or byte_budget < baseline + raster_bytes:
        raise ValueError('Body/face source/coverage exceeds memory budget before allocation')
    ref = P.check_ref(ref)
    if type(analysis) is not dict or analysis.get('face_ref') != ref:
        raise ValueError('Body/face matching needs exact retained canonical source analysis')
    resolved = SUPPORT.resolve(people_state, body_assets, ref, body_bank, analysis,
                               family=FAMILY, operation_id=S.OP)
    if resolved is None:
        raise ValueError('Active body/face matching requires its own reviewed body-skin attachment')
    record, support_key = resolved
    radius, span = BODY._geometry(body_bank, record, (h, w))
    _poll(cancelled)
    body_coverage, body_facts = SUPPORT.raster(people_state, body_assets, ref, body_bank,
        analysis, (h, w), byte_budget=byte_budget-baseline, family=FAMILY, operation_id=S.OP)
    if (body_coverage is None or not body_facts.get('enabled')
            or body_facts.get('support_sha256') != support_key
            or body_facts.get('body_ref') != record['row']['review']['body_ref']
            or body_facts.get('points_sha256') != record['row']['review']['points_sha256']
            or body_facts.get('body_record_sha256') != record['row']['body_record_sha256']):
        raise ValueError('Body/face matching lost or changed its reviewed body support')
    if (type(body_coverage) is not np.ndarray or body_coverage.dtype != np.float32
            or body_coverage.shape != (h, w) or not np.isfinite(body_coverage).all()
            or np.any((body_coverage < 0) | (body_coverage > 1))):
        raise ValueError('Body/face matching needs actual finite current-source body coverage')
    face_coverage, reference = reference_support(ref, analysis, source,
        people_state=people_state, byte_budget=byte_budget, cancelled=cancelled)
    if reference['face_skin_observation'] != record['row']['face_skin_observation']:
        raise ValueError('Body/face reference changed during source preparation')
    if np.any((body_coverage > 0) & (analysis['excluded'] > .1)):
        raise ValueError('Body/face reviewed body support includes known occluded source pixels')
    window = BODY._window(body_coverage, radius); y, x, rh, rw = window
    fy, fx, fh, fw = reference['source_window']
    required = baseline + (rh*rw+fh*fw)*_WINDOW_BYTES_PER_PIXEL + N.memory_estimate((rh, rw), (fh, fw))
    if required > byte_budget:
        raise ValueError('Body/face combined source-window working set exceeds memory budget before allocation')
    _poll(cancelled)
    body_rgb = np.array(source[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
    face_rgb = np.array(source[fy:fy+fh, fx:fx+fw], dtype=np.float32, order='C', copy=True)
    body_coverage = np.array(body_coverage[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
    face_coverage = np.array(face_coverage[fy:fy+fh, fx:fx+fw], dtype=np.float32, order='C', copy=True)
    body_samples, observable = BODY._reference_admission(body_rgb, body_coverage)
    face_samples, _ = FACE._reference_admission(face_rgb, face_coverage)
    for value in (body_rgb, face_rgb, body_coverage, face_coverage):
        value.setflags(write=False)
    _poll(cancelled)
    if not N.available():
        raise RuntimeError('Body/face matching native kernel is unavailable; no Python effect fallback')
    shift = N.prepare(body_rgb, body_coverage, face_rgb, face_coverage, recipe['amount'],
                      radius=radius, cancelled=cancelled or (lambda: False))
    _poll(cancelled)
    changed = BODY._validate_shift(shift, body_coverage, observable)
    field = np.array(shift, dtype=np.float32, order='C', copy=True); field.setflags(write=False)
    count = int(np.count_nonzero(changed)); _poll(cancelled)
    facts = {'operation_id': S.OP, 'control_id': S.CONTROL_ID, 'recipe': recipe,
        'face_ref': ref, 'body_ref': body_facts['body_ref'], 'person_id': body_facts['person_id'],
        'body_support': body_facts, 'reference_support': deepcopy(reference),
        'source_dimensions': [record['source']['width'], record['source']['height']],
        'render_dimensions': [w, h], 'source_window': list(window), 'source_halo': 2*radius+1,
        'scope': 'reviewed-body-to-selected-own-face-effective-source',
        'source_contract': 'immutable-effective-source-working-srgb-sdr',
        'support_method': 'actual-body-skin-intersect-reviewed-region-all-face-and-competing-owner-veto',
        'reference_method': reference['reference_method'],
        'body_reference_samples': body_samples, 'face_reference_samples': face_samples,
        'radius': radius, 'measured_body_span': span,
        'radius_policy': 'ceil(.08*min(current-source-shoulder-span,torso-midpoint-span)); reject outside4..256',
        'field_contract': 'readonly-current-source-HWC2-log-chroma-shift',
        'application': 'pointwise-current-stage-linear-luminance-preserving',
        'changed_pixels': count, 'reason': None if count else 'no-source-chroma-correction',
        'native_solver': 'rust-body-face-match-v1', 'body_to_face_matching': True,
        'reference_is_later_corrected_face': False,
        'review': 'operation-specific-visible-body-own-face-reference-and-canonical-before-after',
        'runtime_quality_accepted': False,
        'limitations': ['manual-assisted-visible-body-ownership-not-automatic-instance-segmentation',
            'effective-source-stage-face-reference-not-later-corrected-face-equivalence',
            'bounded-chroma-matching-not-face-rgb-copying-or-brightness-matching',
            'not-learned-ai-defect-classification-or-lighting-material-separation',
            'natural-colour-lighting-pigment-and-makeup-remain-ambiguous',
            'visible-shoulder-and-hip-scale-required-no-hidden-anatomy-fallback',
            'resampled-semantic-observation-is-not-new-full-resolution-inference',
            'unknown-occlusion-and-model-errors-require-before-after-review']}
    from .people_effects import LocalEffect
    return [LocalEffect(ref, 'body_face_match', window, chroma_shift=field, facts=facts)]
