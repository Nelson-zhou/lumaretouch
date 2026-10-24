# SPDX-License-Identifier: GPL-3.0-or-later
"""Append-only, source-owned manual lower-lid review. AUTHORED / UNRUN.

The existing project bank owns these assets. A painted region is an explicit
human visibility/ownership assertion, never a learned ridge detector. Geometry
only refuses unrelated regions; it cannot establish that a ridge exists.
"""
from copy import deepcopy
import math
import numpy as np

from . import people_state as P, local_mask_recipe as M
from .people_support_assets import content_digest
from .eye_bag_preserve_state import KIND
from .face_scope import _polygon_field

_FIXED_BYTES = 64 * 1024**2
# Whole-grid coverage/eligibility/raw raster plus bounded scan temporaries.
# Polygon distance/interior scratch is admitted separately on ONE eye ROI.
_BYTES_PER_PIXEL = 24
_ROI_BYTES_PER_PIXEL = 256
_MIN_PIXELS = 4
_FOOTPRINT = math.sqrt(.5)


def _poll(cancelled):
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    if cancelled is not None and cancelled():
        raise InterruptedError('Eye-bag review cancelled; no partial support published')


def check_record(record):
    if (type(record) is not dict or set(record) != {'version', 'face_ref', 'source', 'row'}
            or type(record['version']) is not int or record['version'] != 1):
        raise ValueError('Invalid eye-bag preservation review record')
    ref = P.check_ref(record['face_ref'])
    source, row = record['source'], record['row']
    if (type(source) is not dict or set(source) != {'sha256', 'width', 'height'}
            or source['sha256'] != ref['asset_sha256']
            or any(type(source[k]) is not int or not 1 <= source[k] <= 1000000 for k in ('width', 'height'))):
        raise ValueError('Eye-bag review must pin its canonical source and dimensions')
    if (type(row) is not dict or set(row) != {'target', 'landmark_digest', 'eyes'}
            or row['target'] != KIND):
        raise ValueError('An eye-light or other review cannot authorize ridge preservation')
    P.digest(row['landmark_digest'])
    eyes = row['eyes']
    if type(eyes) is not dict or not eyes or set(eyes) - {'left', 'right'}:
        raise ValueError('Review at least one explicit lower-lid side')
    for eye in eyes.values():
        if (type(eye) is not dict or set(eye) != {'recipe', 'visible', 'unoccluded', 'ownership_confirmed'}
                or any(eye[key] is not True for key in ('visible', 'unoccluded', 'ownership_confirmed'))):
            raise ValueError('Confirm this visible, unoccluded lower-lid region belongs to this person')
        recipe = M.check_stack(eye['recipe'])
        if (not recipe['objects'] or any(obj['kind'] != 'brush' or obj['operation'] not in ('add', 'subtract')
                                         or obj['opacity'] != 1
                                         for obj in recipe['objects'])
                or not any(obj['enabled'] and obj['opacity'] > 0 and obj['operation'] == 'add'
                           for obj in recipe['objects'])):
            raise ValueError('Paint the actual source lower-lid region; no full, inferred or placeholder masks')
    if sum(len(obj['points']) for eye in eyes.values() for obj in eye['recipe']['objects']) > 4096:
        raise ValueError('Combined lower-lid brush points exceed the explicit 4096-point review budget')
    return deepcopy(record)


def _face(state, face_ref):
    ref = P.check_ref(face_ref)
    face = state['faces'].get(ref['face_instance_id'])
    if (face is None or P.face_ref(face) != ref or face['evidence']['status'] != 'verified'
            or face['evidence']['backend'] != 'mediapipe'):
        raise ValueError('Eye-bag review requires this exact retained real face analysis')
    return ref, face


def resolve(state, assets, face_ref):
    ref, face = _face(state, face_ref)
    descriptor = face['local_assets'].get(KIND)
    if descriptor is None:
        raise ValueError('Paint and confirm the current person\'s lower-lid preservation region first')
    key = descriptor.get('content_sha256')
    P.digest(key)
    if type(assets) is not dict:
        raise ValueError('Eye-bag review requires the canonical project support bank')
    record = check_record(assets.get(key))
    evidence = face['evidence']
    if (descriptor != {'owner': ref, 'content_sha256': key, 'kind': KIND}
            or content_digest(record) != key or record['face_ref'] != ref
            or record['row']['landmark_digest'] != evidence['landmark_digest']
            or (record['source']['width'], record['source']['height'])
               != (evidence['source_width'], evidence['source_height'])):
        raise ValueError('Eye-bag review is missing, modified, foreign or stale')
    return record, key


def _admission(state, face_ref, analysis, shape, byte_budget):
    from .people_render_runtime import verify_analysis
    from .skin_colour_support import check_analysis_fields
    from .body_pose_evidence import whole_source_shape
    ref, face = _face(state, face_ref)
    if (type(shape) not in (tuple, list) or len(shape) != 2
            or any(type(n) is not int or n < 2 for n in shape)):
        raise ValueError('Eye-bag review needs a whole-source image grid')
    h, w = shape
    if (h*w > M.MAX_PIXELS or type(byte_budget) is not int
            or byte_budget < _FIXED_BYTES + h*w*_BYTES_PER_PIXEL):
        raise ValueError('Eye-bag review exceeds memory admission; no proxy or partial fallback')
    sw, sh = face['evidence']['source_width'], face['evidence']['source_height']
    # Reuse the canonical decoder's exact ALIGN=8 whole-frame contract. Shape
    # still is not pixel provenance; the host authenticates immutable RGB.
    whole_source_shape({'sha256': ref['asset_sha256'], 'width': sw, 'height': sh,
                        'orientation': 'exif_normalized_once'}, (h, w))
    lm = verify_analysis(face, analysis, (h, w))
    observation = check_analysis_fields(analysis, (h, w))
    if observation is None:
        raise ValueError('Eye-bag review needs actual named face-skin evidence, not merged skin')
    for name in ('face_skin', 'excluded'):
        plane = analysis[name]
        if (type(plane) is not np.ndarray or plane.dtype != np.float32 or plane.shape != (h, w)
                or not np.isfinite(plane).all() or np.any((plane < 0) | (plane > 1))):
            raise ValueError('Eye-bag review needs current-grid face skin and known-occluder evidence')
    return ref, face, lm, observation


def _fields(state, face_ref, analysis, shape, eyes, *, byte_budget, cancelled=None):
    """Return coverage, admitted correction support, and non-raster facts.

    Source-edge coordinates match the existing Rust brush raster. At most one
    eye ROI is inspected at a time. Unknown occlusions still require human
    review; source skin is a class mask, not person identity segmentation.
    """
    from .third_party.rapidretouch import under_eye as EYES
    _poll(cancelled)
    ref, face, lm, observation = _admission(state, face_ref, analysis, shape, byte_budget)
    h, w = shape
    points = lm[:, :2].astype(np.float64) * [w, h]
    geos = {side: EYES._eye_geometry(points, spec) for side, spec in EYES.EYES.items()}
    widest = max(geo['eye_w'] for geo in geos.values())
    total_work = sum(M.validate_budget(eye['recipe'], (h, w))['work'] for eye in eyes.values())
    if total_work > M.MAX_WORK:
        raise ValueError('Combined eye-bag reviews exceed the existing vector raster work budget')
    coverage = np.zeros((h, w), np.float32)
    eligible = np.zeros((h, w), bool)
    facts = {}
    for side in ('left', 'right'):
        _poll(cancelled)
        if side not in eyes:
            facts[side] = {'reviewed': False, 'reason': 'unreviewed-side-unchanged'}
            continue
        geo = geos[side]
        width = geo['eye_w']
        lid = geo['lid']
        if (width < EYES.MIN_EYE_PX or width < EYES.FORESHORTENED*widest
                or np.any(lid < 0) or np.any(lid >= [w, h])):
            raise ValueError(side + ' lower lid is clipped, too small or too foreshortened')
        down = EYES._face_down(points)
        # A narrow, conservative LOWER-lid corridor. This is only an admission
        # envelope, not an inferred ridge mask. Do not expand to the bag/cheek.
        ridge = np.concatenate((lid + .06*width*down, (lid + .36*width*down)[::-1]))
        extent = np.concatenate((geo['bag'], geo['bag_crease'], ridge))
        x, y = np.maximum(np.floor(extent.min(axis=0)-1), 0).astype(int)
        x1, y1 = np.minimum(np.ceil(extent.max(axis=0)+1)+1, [w, h]).astype(int)
        x, y, x1, y1 = map(int, (x, y, x1, y1))
        if x1 <= x or y1 <= y:
            raise ValueError(side + ' lower-eye geometry has no source support')
        if _FIXED_BYTES+h*w*_BYTES_PER_PIXEL+(x1-x)*(y1-y)*_ROI_BYTES_PER_PIXEL > byte_budget:
            raise ValueError('Eye-bag geometry ROI exceeds memory admission before polygon allocation')
        xx = np.arange(x, x1, dtype=np.float64)[None, :] + .5
        yy = np.arange(y, y1, dtype=np.float64)[:, None] + .5
        in_face, face_edge = _polygon_field(xx, yy, geo['face'])
        in_ridge, ridge_edge = _polygon_field(xx, yy, ridge)
        in_bag, _ = _polygon_field(xx, yy, geo['bag'])
        in_crease, _ = _polygon_field(xx, yy, geo['bag_crease'])
        eye_hole, eye_edge = _polygon_field(xx, yy, geo['contour'])
        skin = analysis['face_skin'][y:y1, x:x1]
        excluded = analysis['excluded'][y:y1, x:x1]
        owner = in_face & (face_edge > _FOOTPRINT) & (skin >= .5) & (excluded <= .1)
        owner &= ~eye_hole & (eye_edge > _FOOTPRINT)
        raw = M.raster(eyes[side]['recipe'], (h, w))
        if raw.dtype != np.uint8 or raw.shape != (h, w):
            raise ValueError('Eye-bag vector raster returned an invalid source grid')
        for other in state['faces'].values():
            # Disabled/unresolved neighbours still cannot be painted through.
            if other['asset_sha256'] != ref['asset_sha256'] or other['face_instance_id'] == ref['face_instance_id']:
                continue
            left, top, right, bottom = np.asarray(other['box']) * [w, h, w, h]
            bx, by = max(0, int(math.floor(left))), max(0, int(math.floor(top)))
            ex, ey = min(w, int(math.ceil(right))), min(h, int(math.ceil(bottom)))
            if np.any(raw[by:ey, bx:ex]):
                raise ValueError(side + ' painted review crosses another retained person')
            owner &= ~((xx >= left-_FOOTPRINT) & (xx <= right+_FOOTPRINT)
                       & (yy >= top-_FOOTPRINT) & (yy <= bottom+_FOOTPRINT))
        if np.any((raw > 127) & (analysis['excluded'] > .1)):
            raise ValueError(side + ' painted review contradicts known occlusion evidence')
        gate = owner & in_ridge & (ridge_edge > _FOOTPRINT)
        weight = raw[y:y1, x:x1].astype(np.float32) / np.float32(255)
        weight[~gate] = 0
        raw_mass = float(np.sum(raw, dtype=np.float64)) / 255
        admitted_mass = float(np.sum(weight, dtype=np.float64))
        count = int(np.count_nonzero(weight))
        core = int(np.count_nonzero(weight == 1))
        if count < _MIN_PIXELS or core < 1:
            raise ValueError(side + ' review needs a visible hard-core lower-lid region; enlarge the brush or reduce feather')
        if admitted_mass < .5*raw_mass:
            raise ValueError(side + ' review is mostly outside the genuine owned lower-lid corridor; repaint it')
        existing = coverage[y:y1, x:x1]
        if np.any((existing > 0) & (weight > 0)):
            raise ValueError('Left and right lower-lid reviews overlap; do not guess side ownership')
        np.maximum(existing, weight, out=existing)
        eligible[y:y1, x:x1] |= owner & (in_bag | in_crease)
        facts[side] = {'reviewed': True, 'window': [y, x, y1-y, x1-x],
                       'coverage_pixels': count, 'full_coverage_pixels': core,
                       'feather_pixels': int(np.count_nonzero((weight > 0) & (weight < 1))),
                       'clipped_weight': raw_mass-admitted_mass, 'eye_width': float(width)}
    _poll(cancelled)
    coverage.setflags(write=False)
    eligible.setflags(write=False)
    return coverage, eligible, {'sides': facts, 'face_skin_observation': observation,
        'source_dimensions': [face['evidence']['source_width'], face['evidence']['source_height']],
        'render_dimensions': [w, h], 'support_method': 'manual-reviewed-lower-lid-intersect-real-face-skin-and-geometry',
        'automatic_ridge_detection': False, 'unreviewed_sides_unchanged': True,
        'feather_contract': 'existing-local-mask-uint8-coverage; fractional-protection-no-binary-promise'}


def retain(state, assets, face_ref, eyes, *, analysis, byte_budget, cancelled=None):
    """Stage candidate graph and immutable bytes; never commit or own history."""
    out = P.check(state)
    ref, face = _face(out, face_ref)
    if not face['enabled']:
        raise ValueError('Enable this explicitly selected face before retaining a new eye-bag review')
    if type(eyes) is not dict or not eyes:
        raise ValueError('Explicit per-eye review is required')
    # This is the COMPLETE current side map, not a patch. Removing one side
    # must stop treating it; old append-only bytes remain available to history.
    evidence = face['evidence']
    source = {'sha256': ref['asset_sha256'], 'width': evidence['source_width'], 'height': evidence['source_height']}
    record = check_record({'version': 1, 'face_ref': ref, 'source': source,
        'row': {'target': KIND, 'landmark_digest': evidence['landmark_digest'], 'eyes': eyes}})
    if type(analysis) is not dict or type(analysis.get('face_skin')) is not np.ndarray:
        raise ValueError('Current genuine face-skin analysis is required before retaining the review')
    _fields(out, ref, analysis, analysis['face_skin'].shape, record['row']['eyes'],
            byte_budget=byte_budget, cancelled=cancelled)
    key = content_digest(record)
    if type(assets) is not dict:
        raise ValueError('Eye-bag review requires the canonical project support bank')
    bank = deepcopy(assets)
    if key in bank and bank[key] != record:
        raise ValueError('Eye-bag review content digest collision')
    bank[key] = record
    descriptor = {'owner': ref, 'content_sha256': key, 'kind': KIND}
    if face['local_assets'].get(KIND) != descriptor:
        out['faces'][ref['face_instance_id']]['local_assets'][KIND] = descriptor
        out['revision'] += 1
    return P.check(out), bank


def admitted_fields(state, assets, face_ref, shape, *, analysis, byte_budget, cancelled=None):
    record, key = resolve(state, assets, face_ref)
    coverage, eligible, facts = _fields(state, face_ref, analysis, shape, record['row']['eyes'],
                                       byte_budget=byte_budget, cancelled=cancelled)
    return coverage, eligible, {**facts, 'support_sha256': key, 'face_ref': deepcopy(record['face_ref']),
                               'landmark_digest': record['row']['landmark_digest']}


def raster(state, assets, face_ref, shape, *, analysis, byte_budget, cancelled=None):
    coverage, _, facts = admitted_fields(state, assets, face_ref, shape, analysis=analysis,
                                        byte_budget=byte_budget, cancelled=cancelled)
    return coverage, facts


def detach(state, face_ref):
    out = P.check(state)
    ref, face = _face(out, face_ref)
    if KIND in face['local_assets']:
        del out['faces'][ref['face_instance_id']]['local_assets'][KIND]
        out['revision'] += 1
    return P.check(out)


def validate_project(project):
    """Resolve historical/active pointers against the same append-only bank."""
    assets = project.get('people_support_assets', {})
    def visit(value):
        if isinstance(value, dict):
            if 'face_instance_id' in value and KIND in value.get('local_assets', {}):
                state = P.empty()
                state['faces'][value['face_instance_id']] = value
                resolve(P.check(state), assets, P.face_ref(value))
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)
    visit(project)
