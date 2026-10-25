# SPDX-License-Identifier: GPL-3.0-or-later
"""Reviewed same-photo selected-face reference for one target-owned BodyRef.

AUTHORED / UNRUN. This is a separately versioned, body-only storage lane of
control:PC-32465:19, not another colour algorithm. Its review never enables face
matching and no face-only, skin-colour, evenness or body/own-face review enables
it. A selected reference may be the body's owner face or another same-photo
face. Only the target owner's exact manually confirmed person/body link grants
body ownership. Whole-photo semantics and pose boxes never grant ownership.

The canonical people support bank owns metadata and source-normalized manual
brush vectors only. Actual rasters are rebuilt at every render extent. No RGB,
sample statistics, transforms, inferred instance masks or portable donor values
are stored. The host owns source authentication and the reviewed transaction.
"""
from copy import deepcopy
import json
import math

import numpy as np

from . import people_state as P, body_pose_state as B, body_pose_evidence as E
from . import body_pose_operations as O, body_skin_semantics as SEM
from . import local_mask_recipe as M, face_scope as FACE
from . import skin_colour_body_support as BASE
from . import skin_reference_match_support as FACE_SUPPORT
from .people_support_assets import content_digest
from .skin_reference_body_state import OP

KIND = 'skin_reference_match_body_visibility'
SOURCE_STAGE = FACE_SUPPORT.SOURCE_STAGE
FLAGS = ('visible', 'unoccluded', 'ownership_confirmed', 'reference_unchanged')
MAX_RECORD_BYTES = 4 * 1024**2
_MAX_ASSETS = 4096
_MAX_BANK_BYTES = 16 * 1024**2
_FIXED_BYTES = 64 * 1024**2
_BYTES_PER_PIXEL = 48
_ROI_BYTES_PER_PIXEL = 256
_FOOTPRINT_GUARD = math.sqrt(.5) + 1.


def _review(value):
    keys = {'operation_id', 'body_ref', 'points_sha256', 'recipe', *FLAGS}
    if type(value) is not dict or set(value) != keys or value['operation_id'] != OP:
        raise ValueError('Body-reference review must explicitly name this operation and exact BodyRef')
    E.ref(value['body_ref']); E.digest(value['points_sha256'])
    if any(value[key] is not True for key in FLAGS):
        raise ValueError('Confirm visible unoccluded target-owned body skin and unchanged reference face')
    recipe = M.check_stack(value['recipe'])
    if (not recipe['objects'] or any(obj['kind'] != 'brush'
            or obj['operation'] not in ('add', 'subtract') for obj in recipe['objects'])):
        raise ValueError('Body-reference review accepts only source-normalized manual add/subtract brushes')
    if not any(obj['enabled'] and obj['operation'] == 'add' and obj['opacity'] > 0
               for obj in recipe['objects']):
        raise ValueError('Body-reference review needs a positive enabled manual region')
    return {**deepcopy(value), 'recipe': recipe}


def _pair(target_ref, reference_ref):
    target = P.check_ref(target_ref); reference = P.check_ref(reference_ref)
    if target['asset_sha256'] != reference['asset_sha256']:
        raise ValueError('Body-reference matching accepts only the current same photograph')
    if (target['face_instance_id'] == reference['face_instance_id'] and target != reference):
        raise ValueError('One face instance cannot be two different analysis revisions')
    return target, reference


def check_record(record):
    """Strict historical metadata, independent of today's live associations."""
    if (type(record) is not dict or set(record) != {'version', 'face_ref', 'source', 'row'}
            or type(record['version']) is not int or record['version'] != 1):
        raise ValueError('Invalid body-reference support asset')
    O.json_data(record, max_bytes=MAX_RECORD_BYTES)
    row = record['row']
    keys = {'target', 'operation_id', 'source_stage', 'reference_face_ref',
            'face_evidence', 'reference_evidence', 'reference_face_skin_observation',
            'body_record_sha256', 'body_association_revision', 'people_association_revision',
            'body_link', 'face_link', 'observation', 'review'}
    if (type(row) is not dict or set(row) != keys or row['target'] != KIND
            or row['operation_id'] != OP or row['source_stage'] != SOURCE_STAGE):
        raise ValueError('Body-reference support cannot authorize another operation or source stage')
    target, reference = _pair(record['face_ref'], row['reference_face_ref'])
    source = FACE_SUPPORT._source(record['source'], target)
    E.source({**source, 'orientation': E.ORIENTATION})
    evidence = FACE_SUPPORT._evidence(row['face_evidence'], source)
    reference_evidence = FACE_SUPPORT._evidence(row['reference_evidence'], source)
    FACE_SUPPORT._observation(row['reference_face_skin_observation'], reference, reference_evidence)
    if target == reference and evidence != reference_evidence:
        raise ValueError('Own-face body reference has conflicting face evidence')
    review = _review(row['review']); body_ref = review['body_ref']
    if body_ref['asset_sha256'] != source['sha256']:
        raise ValueError('Body-reference review belongs to another source body')
    E.digest(row['body_record_sha256'])
    E.revision(row['body_association_revision']); P.revision(row['people_association_revision'])
    link = row['body_link']; face_link = row['face_link']
    if (type(link) is not dict or set(link) != {'person_id', 'body_ref',
            'people_association_revision', 'confirmation_revision'}
            or E.ref(link['body_ref']) != body_ref):
        raise ValueError('Body-reference support lacks exact body/person confirmation')
    P.token(link['person_id']); E.revision(link['confirmation_revision'])
    P.revision(link['people_association_revision'])
    if (link['people_association_revision'] != row['people_association_revision']
            or link['confirmation_revision'] > row['body_association_revision']):
        raise ValueError('Body-reference body association confirmation is inconsistent')
    if (type(face_link) is not dict or set(face_link) != {'face_instance_id', 'person_id',
            'state', 'confirmation_revision'} or face_link['state'] != 'confirmed'
            or face_link['face_instance_id'] != target['face_instance_id']
            or face_link['person_id'] != link['person_id']):
        raise ValueError('Body-reference support must link the target face, not the selected reference person')
    if P.revision(face_link['confirmation_revision']) > row['people_association_revision']:
        raise ValueError('Body-reference face association confirmation is from the future')
    SEM.check_observation(row['observation'], target, evidence)
    return deepcopy(record)


def _body_analysis(face, analysis, shape=None):
    # Shared evidence/ownership helpers do not read or reuse any other family's
    # review. Actual body_skin is mandatory; merged/face skin cannot substitute.
    observation = BASE._analysis(face, analysis, shape)
    landmarks = np.asarray(analysis['landmarks'], dtype='<f4')
    if np.any((landmarks[:, :2] < -1) | (landmarks[:, :2] > 2)):
        raise ValueError('Body-reference owner landmarks are outside the normalized evidence contract')
    source = {'sha256': face['asset_sha256'], 'width': face['evidence']['source_width'],
              'height': face['evidence']['source_height'], 'orientation': E.ORIENTATION}
    actual_shape = analysis['body_skin'].shape
    E.whole_source_shape(source, actual_shape)
    excluded = analysis.get('excluded')
    if (type(excluded) is not np.ndarray or excluded.dtype != np.float32
            or excluded.shape != actual_shape or not np.isfinite(excluded).all()
            or np.any((excluded < 0) | (excluded > 1))):
        raise ValueError('Body-reference matching needs exact-grid finite known-occluder evidence')
    return observation


def choices(state, body_bank, target_ref, target_analysis):
    """Current explicitly confirmed target-owned bodies only; no pose proximity."""
    state = P.check(state); body_bank = B.check(body_bank)
    ref, face = FACE_SUPPORT._face(state, target_ref)
    _body_analysis(face, target_analysis)
    result = []
    for body in body_bank['bodies'].values():
        body_ref = body['record']['body_ref']
        try:
            row, _ = BASE._ownership(state, body_bank, ref, body_ref)
        except ValueError:
            continue
        result.append({'body_ref': deepcopy(body_ref), 'points_sha256': row['record']['points_sha256'],
                       'source': deepcopy(row['record']['source']), 'association': deepcopy(row['association'])})
    return result


def retain(state, assets, target_ref, reference_ref, body_bank, target_analysis,
           reference_analysis, review, *, confirmed=False):
    """Stage one operation-owned relation; host publishes only reviewed pixels.

    No face-only relation is needed or created, and no scalar amount is changed.
    ``confirmed`` is this exact body/reference review, not generic portrait consent.
    """
    if confirmed is not True:
        raise ValueError('Body-reference matching requires its own explicit review confirmation')
    out = P.check(state); body_bank = B.check(body_bank)
    target_ref, reference_ref = _pair(target_ref, reference_ref)
    _, target = FACE_SUPPORT._face(out, target_ref); _, reference = FACE_SUPPORT._face(out, reference_ref)
    review = _review(review); observation = _body_analysis(target, target_analysis)
    _, reference_observation = FACE_SUPPORT._analysis(reference, reference_analysis)
    if target_analysis['body_skin'].shape != reference_analysis['face_skin'].shape:
        raise ValueError('Body-reference review analyses must use the same whole-source grid')
    body, face_link = BASE._ownership(out, body_bank, target_ref, review['body_ref'])
    measured = body['record']
    if review['points_sha256'] != measured['points_sha256']:
        raise ValueError('Body-reference review names stale measured pose points')
    record = check_record({'version': 1, 'face_ref': target_ref,
        'source': {key: measured['source'][key] for key in ('sha256', 'width', 'height')},
        'row': {'target': KIND, 'operation_id': OP, 'source_stage': SOURCE_STAGE,
            'reference_face_ref': reference_ref, 'face_evidence': deepcopy(target['evidence']),
            'reference_evidence': deepcopy(reference['evidence']),
            'reference_face_skin_observation': reference_observation,
            'body_record_sha256': E.content_digest(measured),
            'body_association_revision': body_bank['association_revision'],
            'people_association_revision': out['association_revision'],
            'body_link': deepcopy(body['association']), 'face_link': deepcopy(face_link),
            'observation': observation, 'review': review}})
    if type(assets) is not dict or len(assets) > _MAX_ASSETS:
        raise ValueError('Body-reference matching needs the canonical project support bank')
    key = content_digest(record); bank = deepcopy(assets)
    if key in bank and bank[key] != record:
        raise ValueError('Immutable body-reference support hash collision')
    if key not in bank and len(bank) >= _MAX_ASSETS:
        raise ValueError('Canonical people support bank is full')
    bank[key] = record
    if len(json.dumps(bank, allow_nan=False).encode()) > _MAX_BANK_BYTES:
        raise ValueError('Canonical people support bank exceeds its byte budget')
    descriptor = {'owner': target_ref, 'content_sha256': key, 'kind': KIND}
    if target['local_assets'].get(KIND) != descriptor:
        target['local_assets'][KIND] = descriptor; out['revision'] += 1
    return P.check(out), bank


def _attached(state, assets, ref):
    _, face = FACE_SUPPORT._face(state, ref, enabled=False)
    descriptor = face['local_assets'].get(KIND)
    if descriptor is None:
        return None
    if type(assets) is not dict:
        raise ValueError('Body-reference support bank is missing')
    key = descriptor['content_sha256']; record = check_record(assets.get(key))
    if (content_digest(record) != key or record['face_ref'] != ref
            or descriptor != {'owner': ref, 'content_sha256': key, 'kind': KIND}):
        raise ValueError('Body-reference support is missing, changed or owned by another face')
    return record, key


def resolve(state, assets, target_ref, body_bank, target_analysis=None, reference_analysis=None):
    """Absent is disabled; stale attached evidence fails, never silently broadens.

    Both analyses absent permits current metadata admission only. Raster/fit must
    supply actual source-bound arrays. Neutral reset must bypass live resolution.
    """
    state = P.check(state); ref, _ = FACE_SUPPORT._face(state, target_ref, enabled=False)
    attached = _attached(state, assets, ref)
    if attached is None:
        return None
    _, face = FACE_SUPPORT._face(state, ref); body_bank = B.check(body_bank)
    record, key = attached; row = record['row']; review = row['review']
    _, reference = FACE_SUPPORT._face(state, row['reference_face_ref'])
    body, face_link = BASE._ownership(state, body_bank, ref, review['body_ref'])
    if (row['face_evidence'] != face['evidence'] or row['reference_evidence'] != reference['evidence']
            or row['body_record_sha256'] != E.content_digest(body['record'])
            or review['points_sha256'] != body['record']['points_sha256']
            or row['body_association_revision'] != body_bank['association_revision']
            or row['people_association_revision'] != state['association_revision']
            or row['body_link'] != body['association'] or row['face_link'] != face_link):
        raise ValueError('Body-reference source/body/person/reference evidence is stale; review again')
    if (target_analysis is None) != (reference_analysis is None):
        raise ValueError('Supply both exact body-reference analysis rows or neither')
    if target_analysis is not None:
        observation = _body_analysis(face, target_analysis)
        _, reference_observation = FACE_SUPPORT._analysis(reference, reference_analysis)
        if (row['observation'] != observation
                or row['reference_face_skin_observation'] != reference_observation
                or target_analysis['body_skin'].shape != reference_analysis['face_skin'].shape):
            raise ValueError('Body-reference semantic observation or whole-source grid changed; review again')
    return record, key


def detach(state, target_ref):
    """Remove only this active pointer, even if stale; preserve immutable history."""
    out = P.check(state); _, face = FACE_SUPPORT._face(out, target_ref, enabled=False)
    if KIND in face['local_assets']:
        del face['local_assets'][KIND]; out['revision'] += 1
    return P.check(out)


def validate_active(state, assets, active_refs, body_bank, analysis_bank=None):
    """Complete active body target set must share one same-photo reference face.

    The reference person's own body is allowed: all face pixels remain protected.
    Caller also reconciles the independently active face-family reference.
    """
    state = P.check(state)
    if type(active_refs) not in (list, tuple) or len(active_refs) > P.MAX_FACES:
        raise ValueError('Body-reference matching needs a bounded complete active target list')
    refs = [P.check_ref(ref) for ref in active_refs]
    if len({ref['face_instance_id'] for ref in refs}) != len(refs):
        raise ValueError('Body-reference active target list contains duplicates')
    if analysis_bank is not None and type(analysis_bank) is not dict:
        raise ValueError('Body-reference analyses must use stable face-instance keys')
    reference = None
    for ref in refs:
        attached = resolve(state, assets, ref, body_bank)
        if attached is None:
            raise ValueError('Every active body-reference target needs its own reviewed relation')
        record, _ = attached; selected = record['row']['reference_face_ref']
        if reference is not None and reference != selected:
            raise ValueError('All active same-photo body targets must agree on one selected reference')
        reference = selected
        if analysis_bank is not None:
            target_row = analysis_bank.get(ref['face_instance_id'])
            reference_row = analysis_bank.get(reference['face_instance_id'])
            if target_row is None or reference_row is None:
                raise ValueError('Active body-reference target/reference analysis is unavailable')
            resolve(state, assets, ref, body_bank, target_row, reference_row)
    return deepcopy(reference)


def _admit(state, assets, target_ref, body_bank, target_analysis, reference_analysis,
           shape, byte_budget, cancelled):
    FACE_SUPPORT._poll(cancelled)
    if (type(shape) not in (tuple, list) or len(shape) != 2
            or any(type(n) is not int or n < 2 for n in shape)):
        raise ValueError('Body-reference coverage needs a whole-source (height,width) grid')
    shape = tuple(shape); h, w = shape
    baseline = _FIXED_BYTES + h*w*_BYTES_PER_PIXEL
    if h*w > M.MAX_PIXELS or type(byte_budget) is not int or byte_budget < baseline:
        raise ValueError('Body-reference coverage exceeds memory budget before raster allocation')
    state = P.check(state)
    attached = resolve(state, assets, target_ref, body_bank, target_analysis, reference_analysis)
    if attached is None:
        raise ValueError('Active body-reference matching needs its own reviewed body attachment')
    record, key = attached
    E.whole_source_shape({**record['source'], 'orientation': E.ORIENTATION}, shape)
    SEM.check_analysis_fields(target_analysis, shape)
    _, reference = FACE_SUPPORT._face(state, record['row']['reference_face_ref'])
    reference_landmarks, _ = FACE_SUPPORT._analysis(reference, reference_analysis, shape)
    # Use the exact float32 geometry whose bytes the evidence digest names.
    target_landmarks = np.array(target_analysis['landmarks'], dtype='<f4', order='C', copy=True)
    extents = [FACE_SUPPORT._extent(lm, shape)[1] for lm in (target_landmarks, reference_landmarks)]
    # Both body and reference output masks fit this admission. Sequential polygon
    # scratch is bounded by the largest ROI, with guard padding for body vetoes.
    largest = max(min(w, x1-x0+4)*min(h, y1-y0+4) for x0, y0, x1, y1 in extents)
    if baseline + largest*_ROI_BYTES_PER_PIXEL > byte_budget:
        raise ValueError('Body-reference face protection exceeds memory budget before raster allocation')
    return state, record, key, shape, target_landmarks, reference_landmarks


def _protect_oval(coverage, landmarks):
    """Veto complete measured face anatomy, even beyond a narrow retained box."""
    h, w = coverage.shape
    oval, (x0, y0, x1, y1) = FACE_SUPPORT._extent(landmarks, (h, w))
    x0, y0 = max(0, x0-2), max(0, y0-2)
    x1, y1 = min(w, x1+2), min(h, y1+2)
    xx = np.arange(x0, x1, dtype=np.float64)[None, :] + .5
    yy = np.arange(y0, y1, dtype=np.float64)[:, None] + .5
    inside, distance = FACE._polygon_field(xx, yy, oval)
    coverage[y0:y1, x0:x1][inside | (distance <= _FOOTPRINT_GUARD)] = 0


def _competitors(state, assets, record):
    result = []
    for face in state['faces'].values():
        ref = P.face_ref(face)
        if ref == record['face_ref'] or ref['asset_sha256'] != record['source']['sha256']:
            continue
        attachments = [_attached(state, assets, ref)]
        attachments.extend(BASE._attached(state, assets, ref, family=family) for family in BASE.FAMILIES)
        for attached in attachments:
            if attached is None:
                continue
            other, _ = attached
            if other['source'] != record['source']:
                raise ValueError('Competing body-reference review has different source dimensions')
            result.append(other)
    return result


def raster(state, assets, target_ref, body_bank, target_analysis, reference_analysis,
           shape, *, byte_budget, cancelled=None):
    """Readonly body HW permission only; no numerical solve or transferred mask."""
    FACE_SUPPORT._poll(cancelled)
    checked = P.check(state); ref, _ = FACE_SUPPORT._face(checked, target_ref, enabled=False)
    if _attached(checked, assets, ref) is None:
        return None, {'enabled': False}
    state, record, key, shape, target_lm, reference_lm = _admit(state, assets, target_ref,
        body_bank, target_analysis, reference_analysis, shape, byte_budget, cancelled)
    others = _competitors(state, assets, record)
    recipes = [record['row']['review']['recipe']] + [other['row']['review']['recipe'] for other in others]
    if sum(M.validate_budget(recipe, shape)['work'] for recipe in recipes) > M.MAX_WORK:
        raise ValueError('Body-reference and competing rasters exceed the aggregate work budget')
    FACE_SUPPORT._poll(cancelled)
    coverage = BASE._manual(recipes[0], shape)
    coverage *= target_analysis['body_skin']
    coverage[target_analysis['excluded'] > .1] = 0
    protected = BASE._protect_faces(coverage, state, record['source']['sha256'])
    _protect_oval(coverage, target_lm)
    if record['face_ref'] != record['row']['reference_face_ref']:
        _protect_oval(coverage, reference_lm)
    for other in others:
        FACE_SUPPORT._poll(cancelled)
        competing = BASE._manual(other['row']['review']['recipe'], shape)
        if np.any((coverage > 0) & (competing > 0)):
            raise ValueError('Reviewed body-reference region overlaps another attached owner; revise manual regions')
        del competing
    if not np.any(coverage > 0):
        raise ValueError('Reviewed body-reference region contains no admitted visible semantic skin')
    window = FACE_SUPPORT._window(coverage)
    coverage = np.ascontiguousarray(coverage, dtype=np.float32); coverage.setflags(write=False)
    row = record['row']; FACE_SUPPORT._poll(cancelled)
    return coverage, {'enabled': True, 'operation_id': OP, 'face_ref': deepcopy(record['face_ref']),
        'reference_face_ref': deepcopy(row['reference_face_ref']), 'body_ref': deepcopy(row['review']['body_ref']),
        'source': deepcopy(record['source']), 'source_stage': SOURCE_STAGE, 'support_sha256': key,
        'source_window': list(window), 'body_record_sha256': row['body_record_sha256'],
        'points_sha256': row['review']['points_sha256'], 'person_id': row['body_link']['person_id'],
        'body_association_revision': row['body_association_revision'],
        'people_association_revision': row['people_association_revision'],
        'semantic_observation': deepcopy(row['observation']), 'protected_face_boxes': protected,
        'protected_measured_face_ovals': 1 if record['face_ref'] == row['reference_face_ref'] else 2,
        'competing_review_count': len(others), 'support_pixels': int(np.count_nonzero(coverage > 0)),
        'scope': 'reviewed-target-owned-body-to-selected-same-photo-face',
        'support_method': 'actual-body-skin-intersect-manual-region-known-occluder-all-face-veto',
        'overlap_policy': 'refuse-positive-competing-owner-manual-coverage',
        'manual_coordinates': 'source-normalized-pixel-edges', 'manual_rasterizer': 'existing-rust-local-mask',
        'reference_face_unchanged_by_this_operation': True, 'runtime_quality_accepted': False,
        'limitations': ['manual-reviewed-ownership-not-automatic-instance-segmentation',
            'unknown-occlusion-and-model-errors-require-before-after-review',
            'resampled-observation-is-not-new-full-resolution-inference']}


def reference_geometry(state, assets, target_ref, body_bank, target_analysis, reference_analysis,
                       shape, *, byte_budget, cancelled=None):
    """Actual selected face HW reference support, not own-body sample transfer.

    Unlike the old body/own-face layer this imports no 64-hard-pixel photometric
    gate. The existing skin-reference Rust fit owns numerical sample admission.
    """
    state, record, key, shape, target_lm, reference_lm = _admit(state, assets, target_ref,
        body_bank, target_analysis, reference_analysis, shape, byte_budget, cancelled)
    ref = record['row']['reference_face_ref']; row = record['row']
    boxes = [face['box'] for face in state['faces'].values()
             if face['asset_sha256'] == ref['asset_sha256'] and P.face_ref(face) != ref]
    other = () if ref == record['face_ref'] else (target_lm,)
    FACE_SUPPORT._poll(cancelled)
    coverage = FACE.selected_face_skin(reference_analysis['face_skin'], reference_lm, other_landmarks=other)
    coverage[reference_analysis['excluded'] > .1] = 0
    oval, extent = FACE_SUPPORT._extent(reference_lm, shape)
    FACE_SUPPORT._protect(coverage, oval, extent, boxes, cancelled)
    window = FACE_SUPPORT._window(coverage); coverage.setflags(write=False)
    FACE_SUPPORT._poll(cancelled)
    return coverage, {'face_ref': deepcopy(ref), 'source': deepcopy(record['source']),
        'source_stage': SOURCE_STAGE, 'support_sha256': key, 'source_window': list(window),
        'landmark_digest': row['reference_evidence']['landmark_digest'],
        'face_skin_observation': deepcopy(row['reference_face_skin_observation']),
        'support_pixels': int(np.count_nonzero(coverage > 0)), 'protected_face_boxes': len(boxes),
        'reference_selection': 'explicit-user-selected-not-auto-brightest',
        'photometric_admission': 'rust-skin-reference-fit-only', 'runtime_quality_accepted': False}


def geometry(state, assets, target_ref, body_bank, target_analysis, reference_analysis,
             shape, *, byte_budget, cancelled=None):
    """Paired readonly body/reference masks on one authentic source grid."""
    body, target = raster(state, assets, target_ref, body_bank, target_analysis, reference_analysis,
                          shape, byte_budget=byte_budget, cancelled=cancelled)
    if body is None:
        raise ValueError('Active body-reference geometry requires reviewed body support')
    reference, facts = reference_geometry(state, assets, target_ref, body_bank, target_analysis,
        reference_analysis, shape, byte_budget=byte_budget, cancelled=cancelled)
    if np.any((body > 0) & (reference > 0)):
        raise ValueError('Body-reference target and reference supports unexpectedly overlap')
    return body, reference, {**target, 'target': target, 'reference': facts}


def validate_project(project):
    """Check historical descriptors under their own nearest canonical bank.

    Historical links do not resolve against current body/person state. This does
    not permit rendering stale evidence, and does not import sibling/private
    support stores. The shared registry separately validates all unbound assets.
    """
    def visit(value, assets):
        if type(value) is dict:
            if 'people_support_assets' in value:
                assets = value['people_support_assets']
                if type(assets) is not dict:
                    raise ValueError('Historical body-reference support bank is invalid')
            if 'face_instance_id' in value and KIND in value.get('local_assets', {}):
                ref = P.check_ref({key: value[key] for key in ('asset_sha256', 'face_instance_id', 'analysis_revision')})
                descriptor = value['local_assets'][KIND]
                if (type(descriptor) is not dict or set(descriptor) != {'owner', 'content_sha256', 'kind'}
                        or descriptor['owner'] != ref or descriptor['kind'] != KIND):
                    raise ValueError('Historical body-reference descriptor ownership changed')
                key = P.digest(descriptor['content_sha256']); record = check_record(assets.get(key))
                if (record['face_ref'] != ref or content_digest(record) != key
                        or record['row']['face_evidence'] != value.get('evidence')):
                    raise ValueError('Historical body-reference support is missing or changed')
            for key, child in value.items():
                if key != 'people_support_assets':
                    visit(child, assets)
        elif type(value) in (list, tuple):
            for child in value:
                visit(child, assets)
    visit(project, {})
