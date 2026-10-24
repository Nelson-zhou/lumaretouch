# SPDX-License-Identifier: GPL-3.0-or-later
"""Reviewed own-body source chroma evenness. AUTHORED / UNRUN.

LNX-REF-PC-32465-C-d5ac2d4606 concerns uneven colour WITHIN body skin; the
adjacent face/body matching requirement is deliberately not implemented here.
The reference is all admitted skin of exactly one reviewed BodyRef/person.
No face pixels, palette, donor, learned defect detector or blanket skin region
is used. Manual visibility/ownership review intersects the actual body-skin
class, then all retained faces and competing ownership are protected.

Scale is measured from the current BodyRef's source-normalized shoulder/hip
landmarks, not manual brush bounds. This conservative torso-scale policy needs
four visible/present in-frame anchors and can refuse a cropped/occluded torso
even when a reviewer can see a limb. It does not invent hidden anatomy.
"""
import math

import numpy as np

from . import people_state as P
from . import body_pose_state as B, body_pose_evidence as E
from . import skin_colour_body_support as SUPPORT
from . import skin_evenness_native as N, body_skin_evenness_state as S

FAMILY = 'body_skin_evenness'
_FIXED_BYTES = 16 * 1024**2
_HOST_BYTES_PER_PIXEL = 48
_RASTER_FIXED_BYTES = 32 * 1024**2
_RASTER_BYTES_PER_PIXEL = 24
_WINDOW_BYTES_PER_PIXEL = 256
_SCALE_ANCHORS = (11, 12, 23, 24)
_MIN_ANCHOR_CONFIDENCE = .5
_REFERENCE_WEIGHT = .75
_MIN_REFERENCE_SAMPLES = 64
_LUMA = np.array([.2126, .7152, .0722], np.float64)


def _poll(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('Body skin evenness cancelled; no partial layer published')


def _geometry(body_bank, record, shape):
    """Current source-grid torso scale from actual retained pose evidence only.

    Radius = ceil(.08 * min(shoulder distance, shoulder-midpoint to hip-midpoint
    distance)); strict 4..256. No clamping, proxy radius, source metadata scale,
    brush-based anatomy, default pose or shoulder-operation review borrowing.
    """
    row = record['row']; review = row['review']
    bank = B.check(body_bank)
    body = B.target(bank, review['body_ref'])
    measured = E.check(body['record'])
    if (not body['enabled'] or measured['body_ref'] != review['body_ref']
            or measured['points_sha256'] != review['points_sha256']
            or E.content_digest(measured) != row['body_record_sha256']):
        raise ValueError('Body skin evenness scale needs the exact current reviewed BodyRef evidence')
    E.whole_source_shape(measured['source'], shape)
    E.whole_source_shape(measured['source'], tuple(reversed(measured['input_dimensions'])))
    h, w = shape
    anchors = []
    for index in _SCALE_ANCHORS:
        point = measured['points'][index]
        if (point['visibility'] < _MIN_ANCHOR_CONFIDENCE
                or point['presence'] < _MIN_ANCHOR_CONFIDENCE
                or not (0 < point['x'] < 1 and 0 < point['y'] < 1)):
            raise ValueError('Body skin evenness scale needs visible, present in-frame shoulder and hip evidence')
        anchors.append((point['x']*w, point['y']*h))
    left_shoulder, right_shoulder, left_hip, right_hip = anchors
    width = math.hypot(left_shoulder[0]-right_shoulder[0], left_shoulder[1]-right_shoulder[1])
    shoulder_mid = tuple((a+b)*.5 for a, b in zip(left_shoulder, right_shoulder))
    hip_mid = tuple((a+b)*.5 for a, b in zip(left_hip, right_hip))
    height = math.hypot(shoulder_mid[0]-hip_mid[0], shoulder_mid[1]-hip_mid[1])
    radius = int(math.ceil(.08 * min(width, height)))
    if not N.MIN_RADIUS <= radius <= N.MAX_RADIUS:
        raise ValueError('Measured body skin evenness radius is outside 4..256; no scale fallback')
    return radius, {'shoulder_span': width, 'torso_midpoint_span': height,
                    'anchor_indices': list(_SCALE_ANCHORS),
                    'minimum_visibility': _MIN_ANCHOR_CONFIDENCE,
                    'minimum_presence': _MIN_ANCHOR_CONFIDENCE}


def _window(coverage, radius):
    """Entire admitted support plus true two-pass halo; never a tile solve.

    Row/column reductions avoid photograph-sized coordinate-index lists. A
    disconnected arm and leg still belong to ONE solve and ONE own-body robust
    reference. The bounding box chooses storage only, never skin ownership.
    """
    rows = np.flatnonzero(np.any(coverage > 0, axis=1))
    columns = np.flatnonzero(np.any(coverage > 0, axis=0))
    if not len(rows) or not len(columns):
        raise ValueError('Body skin evenness has no admitted unoccluded body support')
    h, w = coverage.shape; halo = 2*radius+1
    y0, x0 = max(0, int(rows[0])-halo), max(0, int(columns[0])-halo)
    y1, x1 = min(h, int(rows[-1])+1+halo), min(w, int(columns[-1])+1+halo)
    return (y0, x0, y1-y0, x1-x0)


def _reference_admission(source, coverage):
    """Native-matching reliability guard, NOT a second robust-reference solve.

    At least 64 own-body samples must have coverage*reliability >= .75. Rust
    remains authoritative for robust-reference status 7 and guided-context
    status 8. Neither failure is swallowed or reported as a neutral success.
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
        raise ValueError('Body skin evenness lacks 64 reliable own-body source reference samples')
    return count, reliability > 0


def _validate_shift(shift, coverage, observable):
    if (type(shift) is not np.ndarray or shift.dtype != np.float32
            or shift.shape != (*coverage.shape, 2) or not np.isfinite(shift).all()):
        raise ValueError('Body skin evenness needs finite current-source float32 HWC2 log-chroma shift')
    changed = np.any(shift != 0, axis=2)
    if np.any(changed & ((coverage <= 0) | ~observable)):
        raise ValueError('Body skin evenness native shift changed protected or unobservable source pixels')
    if np.any(np.sum(shift.astype(np.float64)**2, axis=2) > (N.MAX_SHIFT+1e-7)**2):
        raise ValueError('Body skin evenness native log-chroma shift exceeds its vector bound')
    return changed


def prepare(ref, analysis, source, recipe, *, people_state, body_assets, body_bank,
            byte_budget, cancelled=None):
    """One immutable own-body HWC2 field, applied later to CURRENT stage RGB.

    Caller authenticates effective-source/repair bytes and canonical analysis.
    Existing reviewed support authenticates exact face/body/person, observation
    and association revisions. Active intent without this operation's attachment
    refuses; neutral intent does not need analysis, native code or a body bank.
    Every admitted body region participates in one reference/guided solve with
    a genuine 2r+1 source halo, clipped only at actual source-image boundaries.
    Conservative memory admission precedes full-grid and source-window work.
    """
    recipe = S.check(recipe)
    if not S.active(recipe):
        return []
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    _poll(cancelled)
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3
            or source.shape[2] != 3 or min(source.shape[:2]) < 2):
        raise ValueError('Body skin evenness needs current-source float32 working-sRGB RGB')
    h, w = source.shape[:2]
    baseline = h*w*_HOST_BYTES_PER_PIXEL + _FIXED_BYTES
    raster_bytes = h*w*_RASTER_BYTES_PER_PIXEL + _RASTER_FIXED_BYTES
    if type(byte_budget) is not int or byte_budget < baseline + raster_bytes:
        raise ValueError('Body skin evenness source/coverage exceeds memory budget before allocation')
    ref = P.check_ref(ref)
    if (type(analysis) is not dict or analysis.get('face_ref') != ref
            or 'excluded' not in analysis):
        raise ValueError('Body skin evenness needs the exact retained canonical analysis and exclusions')
    resolved = SUPPORT.resolve(people_state, body_assets, ref, body_bank, analysis,
                               family=FAMILY, operation_id=S.OP)
    if resolved is None:
        raise ValueError('Active body skin evenness requires its own reviewed body-skin attachment')
    record, support_key = resolved
    radius, span = _geometry(body_bank, record, (h, w))
    excluded = analysis['excluded']
    if (type(excluded) is not np.ndarray or excluded.dtype != np.float32 or excluded.shape != (h, w)
            or not np.isfinite(excluded).all() or np.any((excluded < 0) | (excluded > 1))):
        raise ValueError('Body skin evenness needs canonical current-grid known-occluder exclusions')
    if not np.isfinite(source).all() or np.any((source < 0) | (source > 1)):
        raise ValueError('Body skin evenness refuses nonfinite or HDR source instead of clipping')
    _poll(cancelled)
    coverage, support_facts = SUPPORT.raster(people_state, body_assets, ref, body_bank,
        analysis, (h, w), byte_budget=byte_budget-baseline, family=FAMILY, operation_id=S.OP)
    if coverage is None or not support_facts.get('enabled'):
        raise ValueError('Active body skin evenness lost its reviewed body-skin attachment')
    if (support_facts.get('support_sha256') != support_key
            or support_facts.get('body_ref') != record['row']['review']['body_ref']
            or support_facts.get('points_sha256') != record['row']['review']['points_sha256']
            or support_facts.get('body_record_sha256') != record['row']['body_record_sha256']):
        raise ValueError('Body skin evenness support changed during source preparation')
    if (type(coverage) is not np.ndarray or coverage.dtype != np.float32 or coverage.shape != (h, w)
            or not np.isfinite(coverage).all() or np.any((coverage < 0) | (coverage > 1))):
        raise ValueError('Body skin evenness needs actual finite current-source body coverage')
    # The family-specific raster applies this same veto for preview overlays
    # and render support. Never silently narrow only the rendered coverage.
    if np.any((coverage > 0) & (excluded > .1)):
        raise ValueError('Body skin evenness reviewed raster includes known-occluded source pixels')
    _poll(cancelled)
    window = _window(coverage, radius)
    y, x, rh, rw = window
    if baseline + rh*rw*_WINDOW_BYTES_PER_PIXEL + N.memory_estimate((rh, rw)) > byte_budget:
        raise ValueError('Body skin evenness source-window working set exceeds memory budget before allocation')
    frozen = np.array(source[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
    frozen.setflags(write=False)
    coverage = np.array(coverage[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
    reference_samples, observable = _reference_admission(frozen, coverage)
    coverage.setflags(write=False)
    _poll(cancelled)
    if not N.available():
        raise RuntimeError('Body skin evenness native kernel is unavailable; no Python effect fallback')
    shift = N.prepare(frozen, coverage, recipe['amount'], radius=radius,
                      cancelled=cancelled or (lambda: False))
    _poll(cancelled)
    changed = _validate_shift(shift, coverage, observable)
    field = np.array(shift, dtype=np.float32, order='C', copy=True)
    field.setflags(write=False)
    _poll(cancelled)
    count = int(np.count_nonzero(changed))
    facts = {
        'operation_id': S.OP, 'control_id': S.CONTROL_ID, 'recipe': recipe,
        'face_ref': ref, 'body_ref': support_facts['body_ref'],
        'person_id': support_facts['person_id'], 'body_support': support_facts,
        'source_dimensions': [record['source']['width'], record['source']['height']],
        'render_dimensions': [w, h], 'source_window': list(window),
        'source_halo': 2*radius+1, 'scope': 'reviewed-own-body-skin-only',
        'source_contract': 'immutable-effective-source-working-srgb-sdr',
        'support_method': 'actual-body-skin-intersect-reviewed-region-all-face-and-competing-owner-veto',
        'reference_method': 'all-admitted-own-body-source-robust-log-chroma-reference',
        'reference_samples': reference_samples, 'radius': radius,
        'measured_body_span': span,
        'radius_policy': 'ceil(.08*min(current-source-shoulder-span,torso-midpoint-span)); reject outside4..256',
        'field_contract': 'readonly-current-source-HWC2-log-chroma-shift',
        'application': 'pointwise-current-stage-linear-luminance-preserving',
        'changed_pixels': count, 'reason': None if count else 'no-source-chroma-correction',
        'native_solver': 'rust-skin-evenness-v1', 'body_to_face_matching': False,
        'review': 'operation-specific-visible-body-review-and-canonical-before-after',
        'runtime_quality_accepted': False,
        'limitations': [
            'manual-assisted-visible-body-ownership-not-automatic-instance-segmentation',
            'original-low-frequency-colour-correction-not-learned-ai-defect-classification',
            'no-face-pixel-reference-body-to-face-or-cross-person-colour-matching',
            'not-skin-blur-exposure-or-lighting-material-separation',
            'natural-colour-lighting-pigment-and-makeup-remain-ambiguous',
            'visible-shoulder-and-hip-scale-required-no-hidden-anatomy-fallback',
            'resampled-semantic-observation-is-not-new-full-resolution-inference',
            'unknown-occlusion-and-model-errors-require-before-after-review',
        ],
    }
    from .people_effects import LocalEffect
    return [LocalEffect(ref, 'body_skin_evenness', window, chroma_shift=field, facts=facts)]
