# SPDX-License-Identifier: GPL-3.0-or-later
"""Operation-owned same-photo target/reference relations. AUTHORED / UNRUN.

The ONE canonical people_support_assets bank owns immutable metadata records.
The reference is explicitly selected, not inherited from a scalar recipe or
ranked by brightness. This v1 grants FACE support only. A body-face, skin-colour
or other review cannot grant this operation consent, and this consent cannot
extend to any body. No RGB, raster, anatomy template or numerical fit is saved.

The host owns the review transaction, its source/repair edit fences, source-byte
provenance and full-source fit. Fits use the immutable source BEFORE repairs and
portrait effects. This module supplies actual face-skin/anatomical permission,
not a photometric admission test; the Rust solver owns evidence reliability.
"""
from copy import deepcopy
import hashlib
import json
import math

import numpy as np

from . import people_state as P, face_scope as FACE, skin_colour_support as SEM
from .people_support_assets import content_digest
from .skin_reference_match_state import OP

KIND = 'skin_reference_match_relation'
SOURCE_STAGE = 'immutable-source-before-repair-and-portrait-v1'
MAX_RECORD_BYTES = 64 * 1024
_MAX_ASSETS = 4096
_MAX_BANK_BYTES = 16 * 1024**2
_MAX_CANVAS_PIXELS = 64_000_000
_FIXED_BYTES = 64 * 1024**2
_BYTES_PER_PIXEL = 32
_ROI_BYTES_PER_PIXEL = 256
_FOOTPRINT = math.sqrt(.5)
_REVIEW = {'confirmed': True, 'scope': 'face-only', 'reference_unchanged': True}


def _poll(cancelled):
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    if cancelled is not None and cancelled():
        raise InterruptedError('Skin-reference support cancelled; no partial support published')


def _source(value, ref):
    if (type(value) is not dict or set(value) != {'sha256', 'width', 'height'}
            or value['sha256'] != ref['asset_sha256']
            or any(type(value[k]) is not int or not 1 <= value[k] <= 1000000
                   for k in ('width', 'height'))):
        raise ValueError('Skin-reference relation needs exact canonical source dimensions')
    P.digest(value['sha256'])
    return deepcopy(value)


def _evidence(value, source):
    evidence = P.check_evidence(value)
    if (evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe'
            or (evidence['source_width'], evidence['source_height'])
            != (source['width'], source['height'])):
        raise ValueError('Skin-reference relation requires exact real same-source face evidence')
    P.digest(evidence['semantic_model_sha256'])
    return evidence


def _observation(value, ref, evidence):
    keys = {'contract', 'source_sha256', 'semantic_model_sha256', 'producer_width', 'producer_height'}
    if (type(value) is not dict or set(value) != keys or value['contract'] != SEM.CONTRACT
            or value['source_sha256'] != ref['asset_sha256']
            or value['semantic_model_sha256'] != evidence['semantic_model_sha256']
            or any(type(value[k]) is not int or not 1 <= value[k] <= 1000000
                   for k in ('producer_width', 'producer_height'))):
        raise ValueError('Skin-reference relation needs each exact face_skin source/model observation')
    return deepcopy(value)


def _pair(target_ref, reference_ref):
    target = P.check_ref(target_ref); reference = P.check_ref(reference_ref)
    if (target['asset_sha256'] != reference['asset_sha256']
            or target['face_instance_id'] == reference['face_instance_id']):
        raise ValueError('Select a distinct reference face from the same photograph')
    return target, reference


def check_record(record):
    """Check historical JSON independently of today's face graph/analysis bank."""
    if (type(record) is not dict or set(record) != {'version', 'face_ref', 'source', 'row'}
            or type(record['version']) is not int or record['version'] != 1):
        raise ValueError('Invalid skin-reference relation envelope')
    row = record['row']
    keys = {'target', 'operation_id', 'source_stage', 'reference_face_ref',
            'target_evidence', 'reference_evidence', 'target_landmark_digest',
            'reference_landmark_digest', 'target_face_skin_observation',
            'reference_face_skin_observation', 'review'}
    if (type(row) is not dict or set(row) != keys or row['target'] != KIND
            or row['operation_id'] != OP or row['source_stage'] != SOURCE_STAGE):
        raise ValueError('Skin-reference review cannot authorize another operation or source stage')
    target, reference = _pair(record['face_ref'], row['reference_face_ref'])
    source = _source(record['source'], target)
    for name, ref in (('target', target), ('reference', reference)):
        evidence = _evidence(row[name + '_evidence'], source)
        if P.digest(row[name + '_landmark_digest']) != evidence['landmark_digest']:
            raise ValueError('Skin-reference relation landmark identities disagree')
        _observation(row[name + '_face_skin_observation'], ref, evidence)
    review = row['review']
    if (type(review) is not dict or set(review) != set(_REVIEW)
            or review['confirmed'] is not True or review['reference_unchanged'] is not True
            or type(review['scope']) is not str or review['scope'] != 'face-only'):
        raise ValueError('Confirm this operation-specific face-only relation and unchanged reference')
    try:
        encoded = json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (ValueError, TypeError) as exc:
        raise ValueError('Skin-reference relation must contain JSON metadata only') from exc
    if len(encoded) > MAX_RECORD_BYTES:
        raise ValueError('Skin-reference relation exceeds its metadata budget')
    return deepcopy(record)


def _face(state, face_ref, *, enabled=True):
    ref = P.check_ref(face_ref)
    face = state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref:
        raise ValueError('Skin-reference face changed; never rebind by order or person group')
    if enabled and not face['enabled']:
        raise ValueError('Skin-reference target and reference must both be enabled')
    return ref, face


def _whole_shape(source, shape):
    # The existing canonical decoder contract admits its ALIGN=8 preview grid;
    # source dimensions remain original/effective-source dimensions, never ROI.
    from .body_pose_evidence import whole_source_shape
    whole_source_shape({**source, 'orientation': 'exif_normalized_once'}, shape)


def _analysis(face, analysis, shape=None):
    ref = P.face_ref(face)
    if (type(analysis) is not dict or analysis.get('face_ref') != ref
            or analysis.get('evidence') != face['evidence']):
        raise ValueError('Skin-reference analysis differs from its exact retained face/source')
    source = {'sha256': ref['asset_sha256'], 'width': face['evidence']['source_width'],
              'height': face['evidence']['source_height']}
    evidence = _evidence(analysis['evidence'], source)
    landmarks = np.array(analysis.get('landmarks'), dtype='<f4', order='C', copy=True)
    if (landmarks.shape != (478, 3) or not np.isfinite(landmarks).all()
            or np.any((landmarks[:, :2] < -1) | (landmarks[:, :2] > 2))
            or hashlib.sha256(landmarks.tobytes()).hexdigest() != evidence['landmark_digest']):
        raise ValueError('Skin-reference anatomy differs from its verified normalized478 digest')
    observation = SEM.check_analysis_fields(analysis, shape)
    if observation is None:
        raise ValueError('Skin-reference matching needs actual face_skin, not merged/body skin')
    actual_shape = analysis['face_skin'].shape
    _whole_shape(source, actual_shape)
    excluded = analysis.get('excluded')
    if (type(excluded) is not np.ndarray or excluded.dtype != np.float32
            or excluded.shape != actual_shape or not np.isfinite(excluded).all()
            or np.any((excluded < 0) | (excluded > 1))):
        raise ValueError('Skin-reference matching needs exact-grid known-occluder evidence')
    return landmarks, _observation(observation, ref, evidence)


def retain(state, assets, target_ref, reference_ref, target_analysis, reference_analysis, *, confirmed=False):
    """Stage reviewed metadata/pointer; host publishes only its fenced transaction.

    ``confirmed=True`` represents this operation's explicit source-overlay and
    before/after review, not a generic portrait/body consent. Calls are pure;
    existing records are append-only and no scalar override is changed.
    """
    if confirmed is not True:
        raise ValueError('Skin-reference matching needs its own explicit face-only review confirmation')
    out = P.check(state)
    target_ref, reference_ref = _pair(target_ref, reference_ref)
    _, target = _face(out, target_ref); _, reference = _face(out, reference_ref)
    _, target_observation = _analysis(target, target_analysis)
    _, reference_observation = _analysis(reference, reference_analysis)
    if target_analysis['face_skin'].shape != reference_analysis['face_skin'].shape:
        raise ValueError('Skin-reference review analyses must use the same whole-source grid')
    source = {'sha256': target_ref['asset_sha256'], 'width': target['evidence']['source_width'],
              'height': target['evidence']['source_height']}
    record = check_record({'version': 1, 'face_ref': target_ref, 'source': source, 'row': {
        'target': KIND, 'operation_id': OP, 'source_stage': SOURCE_STAGE,
        'reference_face_ref': reference_ref,
        'target_evidence': target['evidence'], 'reference_evidence': reference['evidence'],
        'target_landmark_digest': target['evidence']['landmark_digest'],
        'reference_landmark_digest': reference['evidence']['landmark_digest'],
        'target_face_skin_observation': target_observation,
        'reference_face_skin_observation': reference_observation, 'review': deepcopy(_REVIEW)}})
    if type(assets) is not dict or len(assets) > _MAX_ASSETS:
        raise ValueError('Skin-reference matching needs the canonical project support bank')
    key = content_digest(record); bank = deepcopy(assets)
    if key in bank and bank[key] != record:
        raise ValueError('Immutable skin-reference relation hash collision')
    if key not in bank and len(bank) >= _MAX_ASSETS:
        raise ValueError('Canonical people support bank is full')
    bank[key] = record
    if len(json.dumps(bank, allow_nan=False).encode()) > _MAX_BANK_BYTES:
        raise ValueError('Canonical people support bank exceeds its byte budget')
    descriptor = {'owner': target_ref, 'content_sha256': key, 'kind': KIND}
    if target['local_assets'].get(KIND) != descriptor:
        target['local_assets'][KIND] = descriptor
        out['revision'] += 1
    return P.check(out), bank


def resolve(state, assets, target_ref, target_analysis=None, reference_analysis=None):
    """Missing relation is None; stale/foreign attached consent is an error.

    With both analyses absent this authenticates current retained metadata only.
    Geometry/render must supply both actual analysis rows, not use metadata-only
    resolution as permission to manufacture support.
    """
    state = P.check(state); ref, face = _face(state, target_ref, enabled=False)
    descriptor = face['local_assets'].get(KIND)
    if descriptor is None:
        return None
    if type(assets) is not dict:
        raise ValueError('Skin-reference matching needs the canonical project support bank')
    key = descriptor['content_sha256']; record = check_record(assets.get(key))
    if (content_digest(record) != key or record['face_ref'] != ref
            or descriptor != {'owner': ref, 'content_sha256': key, 'kind': KIND}):
        raise ValueError('Skin-reference relation is missing, modified or owned by another target')
    _, face = _face(state, ref)
    row = record['row']; _, reference = _face(state, row['reference_face_ref'])
    if row['target_evidence'] != face['evidence'] or row['reference_evidence'] != reference['evidence']:
        raise ValueError('Skin-reference target/reference evidence changed; review this relation again')
    if (target_analysis is None) != (reference_analysis is None):
        raise ValueError('Supply both exact skin-reference analysis rows or neither')
    if target_analysis is not None:
        _, target_observation = _analysis(face, target_analysis)
        _, reference_observation = _analysis(reference, reference_analysis)
        if (target_observation != row['target_face_skin_observation']
                or reference_observation != row['reference_face_skin_observation']
                or target_analysis['face_skin'].shape != reference_analysis['face_skin'].shape):
            raise ValueError('Skin-reference semantic observation or whole-source grid changed; review again')
    return record, key


def detach(state, target_ref):
    """Remove only the pointer, even if stale/disabled; preserve immutable history."""
    out = P.check(state); _, face = _face(out, target_ref, enabled=False)
    if KIND in face['local_assets']:
        del face['local_assets'][KIND]
        out['revision'] += 1
    return P.check(out)


def validate_active(state, assets, active_refs, analysis_bank=None):
    """All final active targets in one photo must share ONE non-target reference.

    The caller derives the complete list from resolved nonzero scalar amounts,
    including inherited amounts. No list of user-selected rows is sufficient.
    This is not a per-person/group recipe reference, and inactive old relations
    may remain attached for undo without blocking neutral operation.
    """
    state = P.check(state)
    if type(active_refs) not in (list, tuple) or len(active_refs) > P.MAX_FACES:
        raise ValueError('Skin-reference matching needs a bounded complete active target list')
    refs = [P.check_ref(ref) for ref in active_refs]
    if len({ref['face_instance_id'] for ref in refs}) != len(refs):
        raise ValueError('Skin-reference active target list contains duplicates')
    if analysis_bank is not None and type(analysis_bank) is not dict:
        raise ValueError('Skin-reference analysis bank must use stable face-instance keys')
    reference = None
    for ref in refs:
        attached = resolve(state, assets, ref)
        if attached is None:
            raise ValueError('Every active skin-reference target needs its own reviewed relation')
        record, _ = attached; selected = record['row']['reference_face_ref']
        if reference is not None and reference != selected:
            raise ValueError('All active same-photo targets must agree on one selected reference')
        reference = selected
        if analysis_bank is not None:
            target_row = analysis_bank.get(ref['face_instance_id'])
            reference_row = analysis_bank.get(reference['face_instance_id'])
            if target_row is None or reference_row is None:
                raise ValueError('Active skin-reference target/reference analysis is unavailable')
            resolve(state, assets, ref, target_row, reference_row)
    if reference is not None and any(ref['face_instance_id'] == reference['face_instance_id'] for ref in refs):
        raise ValueError('The selected reference face must stay unchanged by this operation')
    return deepcopy(reference)


def _extent(landmarks, shape):
    h, w = shape
    oval = landmarks[list(FACE.FACE_OVAL), :2].astype(np.float64) * [w, h]
    low = np.maximum(np.floor(oval.min(axis=0)).astype(int), 0)
    high = np.minimum(np.ceil(oval.max(axis=0)).astype(int) + 1, [w, h])
    if np.any(high <= low):
        raise ValueError('Skin-reference face has no measured source interior')
    return oval, tuple(int(v) for v in (*low, *high))


def _protect(coverage, oval, extent, boxes, cancelled):
    """Inset full outer pixel footprints; foreign boxes are vetoes, not owners."""
    h, w = coverage.shape; x0, y0, x1, y1 = extent
    xx = np.arange(x0, x1, dtype=np.float64)[None, :] + .5
    yy = np.arange(y0, y1, dtype=np.float64)[:, None] + .5
    inside, distance = FACE._polygon_field(xx, yy, oval)
    feather = max(1., .015 * float(np.max(np.ptp(oval, axis=0))))
    coverage[y0:y1, x0:x1] *= inside * np.clip((distance - _FOOTPRINT)/feather, 0, 1)
    for box in boxes:
        _poll(cancelled)
        left, top, right, bottom = np.asarray(box, dtype=np.float64) * [w, h, w, h]
        feather = max(1., .015 * max(right - left, bottom - top))
        pad = feather + _FOOTPRINT + 1
        bx0, by0 = max(x0, int(math.floor(left - pad))), max(y0, int(math.floor(top - pad)))
        bx1, by1 = min(x1, int(math.ceil(right + pad))), min(y1, int(math.ceil(bottom + pad)))
        if bx1 <= bx0 or by1 <= by0:
            continue
        xx = np.arange(bx0, bx1, dtype=np.float64)[None, :] + .5
        yy = np.arange(by0, by1, dtype=np.float64)[:, None] + .5
        dx = np.maximum(np.maximum(left - xx, xx - right), 0)
        dy = np.maximum(np.maximum(top - yy, yy - bottom), 0)
        coverage[by0:by1, bx0:bx1] *= np.clip((np.hypot(dx, dy) - _FOOTPRINT)/feather, 0, 1)


def _window(coverage):
    rows = np.flatnonzero(np.any(coverage > 0, axis=1))
    columns = np.flatnonzero(np.any(coverage > 0, axis=0))
    if not len(rows) or not len(columns):
        raise ValueError('Skin-reference relation has no actual unprotected face-skin support')
    # A geometric window is not photometric admission. No old 64-hard-pixel,
    # guided-radius or hard confidence gate is imported into this operation.
    return (int(rows[0]), int(columns[0]), int(rows[-1] - rows[0] + 1),
            int(columns[-1] - columns[0] + 1))


def geometry(state, assets, target_ref, target_analysis, reference_analysis, shape, *, byte_budget, cancelled=None):
    """Actual readonly target/reference HW masks and independent full-source ROIs.

    No RGB argument, resizing, pixel pairing, donor copying or numerical fit.
    Grid shape alone is not source authentication: the host must supply actual
    immutable original/effective-source pixels, before repair/portrait stages.
    """
    _poll(cancelled)
    if (type(shape) not in (tuple, list) or len(shape) != 2
            or any(type(n) is not int or n < 2 for n in shape)):
        raise ValueError('Skin-reference support needs a whole-source (height,width) grid')
    h, w = shape; baseline = _FIXED_BYTES + h*w*_BYTES_PER_PIXEL
    if h*w > _MAX_CANVAS_PIXELS or type(byte_budget) is not int or byte_budget < baseline:
        raise ValueError('Skin-reference whole-source support exceeds memory budget before allocation')
    state = P.check(state)
    attached = resolve(state, assets, target_ref)
    if attached is None:
        raise ValueError('Active skin-reference matching requires its own reviewed target relation')
    record, key = attached; row = record['row']; reference_ref = row['reference_face_ref']
    _whole_shape(record['source'], (h, w))
    target_ref, target = _face(state, target_ref); _, reference = _face(state, reference_ref)
    target_landmarks, target_observation = _analysis(target, target_analysis, (h, w))
    reference_landmarks, reference_observation = _analysis(reference, reference_analysis, (h, w))
    if (target_observation != row['target_face_skin_observation']
            or reference_observation != row['reference_face_skin_observation']):
        raise ValueError('Skin-reference semantic observation changed; review the exact relation again')
    target_oval, target_extent = _extent(target_landmarks, (h, w))
    reference_oval, reference_extent = _extent(reference_landmarks, (h, w))
    largest_roi = max((x1 - x0)*(y1 - y0) for x0, y0, x1, y1 in (target_extent, reference_extent))
    if baseline + largest_roi*_ROI_BYTES_PER_PIXEL > byte_budget:
        raise ValueError('Skin-reference anatomical ROI exceeds memory budget before allocation')
    result = []; details = {}
    for name, ref, analysis, landmarks, other, oval, extent in (
            ('target', target_ref, target_analysis, target_landmarks, reference_landmarks, target_oval, target_extent),
            ('reference', reference_ref, reference_analysis, reference_landmarks, target_landmarks, reference_oval, reference_extent)):
        _poll(cancelled)
        boxes = [face['box'] for face in state['faces'].values()
                 if face['asset_sha256'] == ref['asset_sha256'] and P.face_ref(face) != ref]
        # Counterpart's ENTIRE measured oval is protected even if its semantic
        # skin has holes or its retained box is too narrow. All other retained
        # same-source boxes are protective vetoes, including disabled/unresolved.
        coverage = FACE.selected_face_skin(analysis['face_skin'], landmarks, other_landmarks=(other,))
        coverage[analysis['excluded'] > .1] = 0
        _protect(coverage, oval, extent, boxes, cancelled)
        window = _window(coverage)
        coverage.setflags(write=False)
        result.append(coverage)
        details[name] = {'face_ref': deepcopy(ref), 'source_window': list(window),
                         'landmark_digest': analysis['evidence']['landmark_digest'],
                         'face_skin_observation': deepcopy(analysis['face_skin_observation']),
                         'support_pixels': int(np.count_nonzero(coverage > 0)),
                         'protected_face_boxes': len(boxes)}
    if np.any((result[0] > 0) & (result[1] > 0)):
        raise ValueError('Skin-reference target and reference supports unexpectedly overlap')
    _poll(cancelled)
    facts = {'operation_id': OP, 'support_sha256': key, 'source': deepcopy(record['source']),
             'source_stage': SOURCE_STAGE, 'source_dimensions': [record['source']['width'], record['source']['height']],
             'render_dimensions': [w, h], 'scope': 'reviewed-selected-same-photo-face-only',
             'body_extension': {'enabled': False, 'reason': 'requires-separate-operation-specific-body-consent'},
             'support_method': 'actual-face-skin-intersect-measured-anatomy-known-occluder-and-foreign-face-veto',
             'reference_selection': 'explicit-user-selected-not-auto-brightest',
             'reference_face_unchanged_by_this_operation': True, 'runtime_quality_accepted': False,
             'photometric_admission': 'rust-skin-reference-fit-only',
             'limitations': ['face-only-not-whole-AI-multi-person-feature',
                             'semantic-class-and-anatomy-not-person-instance-segmentation',
                             'unknown-occlusion-and-model-errors-require-before-after-review',
                             'resampled-observation-is-not-new-full-resolution-inference'], **details}
    return result[0], result[1], facts
