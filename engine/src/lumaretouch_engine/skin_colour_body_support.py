# SPDX-License-Identifier: GPL-3.0-or-later
"""Reviewed body-skin coverage in the ONE canonical people support bank.

Each descriptor is explicit, nonportable support for exactly one allowlisted
scalar family. Skin-colour, skin-finish, body-evenness and body/face reviews never
authorize one another. This is not a second recipe owner, pose operation or
instance segmenter. Body evenness is body-region colour unevenness only, not
body-to-face colour matching or a learned correction model.
The host stages ``retain`` privately, previews real coverage/pixels, and attaches
the candidate only after its independently fenced confirmation transaction.

Historical records are structurally checkable without today's live association.
Active resolution additionally requires the exact current face/body/person,
source, model observation and association confirmations. Rust's existing manual
mask rasterizer rebuilds vectors at each render extent; no proxy raster is saved.
AUTHORED / UNRUN: this module does not constitute runtime or image acceptance.
"""
from copy import deepcopy
import json
import math
import numpy as np
from . import people_state as S, body_pose_state as B, body_pose_evidence as E
from . import body_pose_operations as O, local_mask_recipe as M
from . import body_skin_semantics as SEM
from .people_support_assets import content_digest

KIND = 'skin_colour_body_visibility'
OPERATION = 'lnx.skin_colour.v1'
FINISH_KIND = 'skin_finish_body_visibility'
FINISH_OPERATION = 'lnx.skin_finish.v1'
EVENNESS_KIND = 'body_skin_evenness_visibility'
EVENNESS_OPERATION = 'lnx.body_skin_evenness.v1'
FACE_MATCH_KIND = 'body_face_match_visibility'
FACE_MATCH_OPERATION = 'lnx.body_face_match.v1'
FAMILIES = ('skin_colour', 'skin_finish', 'body_skin_evenness', 'body_face_match')
FLAGS = ('visible', 'unoccluded', 'ownership_confirmed')
MAX_RECORD_BYTES = 4 * 1024 * 1024


def family_spec(family='skin_colour', operation_id=None):
    """Exact family/operation allowlist; no descriptor or authorization aliases."""
    if type(family) is not str or family not in FAMILIES:
        raise ValueError('Unknown body-skin scalar family')
    kind, operation = {'skin_colour': (KIND, OPERATION),
                       'skin_finish': (FINISH_KIND, FINISH_OPERATION),
                       'body_skin_evenness': (EVENNESS_KIND, EVENNESS_OPERATION),
                       'body_face_match': (FACE_MATCH_KIND, FACE_MATCH_OPERATION)}[family]
    if operation_id is not None and (type(operation_id) is not str or operation_id != operation):
        raise ValueError('Body-skin family cannot authorize another operation')
    return kind, operation


def _review(value):
    keys = {'body_ref', 'points_sha256', 'recipe', *FLAGS}
    if type(value) is not dict or set(value) != keys:
        raise ValueError('Body-skin review must name its exact body, points and manual region')
    E.ref(value['body_ref']); E.digest(value['points_sha256'])
    if any(value[key] is not True for key in FLAGS):
        raise ValueError('Confirm visible, unoccluded skin belonging to this exact body/person')
    recipe = M.check_stack(value['recipe'])
    if (not recipe['objects'] or any(obj['kind'] != 'brush'
            or obj['operation'] not in ('add', 'subtract') for obj in recipe['objects'])):
        raise ValueError('Body-skin review accepts only source-normalized manual add/subtract brushes')
    if not any(obj['enabled'] and obj['operation'] == 'add' and obj['opacity'] > 0
               for obj in recipe['objects']):
        raise ValueError('Body-skin review needs a positive enabled manual region')
    return {**deepcopy(value), 'recipe': recipe}


def _face_observation(value, ref, evidence):
    """Historical own-face reference identity, never donor pixels or a mask."""
    from .skin_colour_support import CONTRACT
    keys = {'contract', 'source_sha256', 'semantic_model_sha256', 'producer_width', 'producer_height'}
    if (type(value) is not dict or set(value) != keys or value['contract'] != CONTRACT
            or value['source_sha256'] != ref['asset_sha256']
            or value['semantic_model_sha256'] != evidence['semantic_model_sha256']):
        raise ValueError('Body/face reference needs the exact own-face semantic source/model observation')
    S.digest(value['semantic_model_sha256'])
    if any(type(value[k]) is not int or not 1 <= value[k] <= 1000000
           for k in ('producer_width', 'producer_height')):
        raise ValueError('Body/face reference observation extent is invalid')
    return deepcopy(value)


def _reference_observation(face, analysis):
    from .skin_colour_support import check_analysis_fields
    observation = check_analysis_fields(analysis)
    if observation is None:
        raise ValueError('Body/face matching requires actual own face_skin observation; no merged/donor fallback')
    return _face_observation(observation, S.face_ref(face), face['evidence'])


def reference_identity(face_ref, face_evidence, face_skin_observation):
    """Own-source metadata identity only; not raster/sample observability proof."""
    ref = S.check_ref(face_ref); evidence = S.check_evidence(face_evidence)
    if evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe':
        raise ValueError('Body/face reference identity requires the verified selected face')
    return {'face_ref': ref, 'face_skin_observation': _face_observation(face_skin_observation, ref, evidence),
            'landmark_digest': evidence['landmark_digest'],
            'reference_method': 'effective-source-stage-own-face-robust-log-chroma'}


def check_record(record, *, family='skin_colour', operation_id=None):
    """Validate immutable JSON only; never resolve history against a live bank."""
    kind, operation = family_spec(family, operation_id)
    if (type(record) is not dict or set(record) != {'version', 'face_ref', 'source', 'row'}
            or type(record['version']) is not int or record['version'] != 1):
        raise ValueError('Invalid body-skin review asset')
    O.json_data(record, max_bytes=MAX_RECORD_BYTES)
    ref = S.check_ref(record['face_ref']); source = record['source']; row = record['row']
    if type(source) is not dict or set(source) != {'sha256', 'width', 'height'}:
        raise ValueError('Body-skin asset needs canonical source dimensions')
    frame = E.source({**source, 'orientation': E.ORIENTATION})
    if frame['sha256'] != ref['asset_sha256']:
        raise ValueError('Body-skin asset and face source differ')
    keys = {'target', 'operation_id', 'face_evidence', 'body_record_sha256',
            'body_association_revision', 'people_association_revision',
            'body_link', 'face_link', 'observation', 'review'}
    if family == 'body_face_match':
        keys.add('face_skin_observation')
    if (type(row) is not dict or set(row) != keys or row['target'] != kind
            or row['operation_id'] != operation):
        raise ValueError('Body-skin support cannot authorize another operation')
    review = _review(row['review']); body_ref = review['body_ref']
    if body_ref['asset_sha256'] != source['sha256']:
        raise ValueError('Body-skin review belongs to another source body')
    evidence = S.check_evidence(row['face_evidence'])
    if (evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe'
            or (evidence['source_width'], evidence['source_height']) != (source['width'], source['height'])):
        raise ValueError('Body-skin review needs source-owned real face evidence')
    E.digest(row['body_record_sha256'])
    E.revision(row['body_association_revision']); S.revision(row['people_association_revision'])
    link = row['body_link']; face_link = row['face_link']
    if (type(link) is not dict or set(link) != {'person_id', 'body_ref',
            'people_association_revision', 'confirmation_revision'}
            or E.ref(link['body_ref']) != body_ref):
        raise ValueError('Body-skin record lacks an exact body/person confirmation')
    S.token(link['person_id']); E.revision(link['confirmation_revision'])
    S.revision(link['people_association_revision'])
    if (link['people_association_revision'] != row['people_association_revision']
            or link['confirmation_revision'] > row['body_association_revision']):
        raise ValueError('Body-skin association confirmation is inconsistent')
    if (type(face_link) is not dict or set(face_link) != {'face_instance_id', 'person_id',
            'state', 'confirmation_revision'} or face_link['state'] != 'confirmed'
            or face_link['face_instance_id'] != ref['face_instance_id']
            or face_link['person_id'] != link['person_id']):
        raise ValueError('Body-skin record lacks the same confirmed face/person')
    if S.revision(face_link['confirmation_revision']) > row['people_association_revision']:
        raise ValueError('Body-skin face confirmation is from the future')
    SEM.check_observation(row['observation'], ref, evidence)
    if family == 'body_face_match':
        _face_observation(row['face_skin_observation'], ref, evidence)
    return deepcopy(record)


def _face(state, face_ref, *, enabled=True):
    ref = S.check_ref(face_ref); face = state['faces'].get(ref['face_instance_id'])
    if face is None or S.face_ref(face) != ref:
        raise ValueError('Body-skin target face changed; never retarget by list position')
    if enabled and not face['enabled']:
        raise ValueError('Body-skin target face is disabled')
    return ref, face


def _analysis(face, analysis, shape=None):
    ref = S.face_ref(face)
    if (type(analysis) is not dict or analysis.get('face_ref') != ref
            or analysis.get('evidence') != face['evidence']):
        raise ValueError('Body-skin observation belongs to another face/source analysis')
    from .people_binding import landmark_digest
    if landmark_digest(analysis.get('landmarks')) != face['evidence']['landmark_digest']:
        raise ValueError('Body-skin face landmark evidence changed')
    observation = SEM.check_analysis_fields(analysis, shape)
    if observation is None:
        raise ValueError('Actual body_skin semantic observation is missing; no face/merged-skin fallback')
    return observation


def _ownership(state, body_bank, ref, body_ref):
    row = B.target(body_bank, body_ref); record = E.check(row['record'])
    E.whole_source_shape(record['source'], tuple(reversed(record['input_dimensions'])))
    if not row['enabled'] or body_ref['asset_sha256'] != ref['asset_sha256']:
        raise ValueError('Body-skin requires an enabled exact-source retained body')
    face = state['faces'][ref['face_instance_id']]; e = face['evidence']
    expected = {'sha256': ref['asset_sha256'], 'width': e['source_width'],
                'height': e['source_height'], 'orientation': e['orientation']}
    if record['source'] != expected:
        raise ValueError('Body-skin body/face source dimensions or orientation differ')
    link = row['association']
    if (link is None or link['person_id'] not in state['persons']
            or link['people_association_revision'] != state['association_revision']):
        raise ValueError('Body-skin requires a current explicit body/person association')
    matches = [item for item in state['links'] if item['state'] == 'confirmed'
               and item['person_id'] == link['person_id']
               and state['faces'][item['face_instance_id']]['asset_sha256'] == ref['asset_sha256']]
    if len(matches) != 1 or matches[0]['face_instance_id'] != ref['face_instance_id']:
        raise ValueError('Body-skin needs exactly this one confirmed source face for the body person')
    return row, matches[0]


def choices(state, body_bank, face_ref, analysis, *, family='skin_colour', operation_id=None):
    """Only explicitly associated bodies; never infer from boxes or pose proximity."""
    family_spec(family, operation_id)
    state = S.check(state); body_bank = B.check(body_bank); ref, face = _face(state, face_ref)
    _analysis(face, analysis)
    if family == 'body_face_match':
        _reference_observation(face, analysis)
    result = []
    for body in body_bank['bodies'].values():
        body_ref = body['record']['body_ref']
        try:
            row, _ = _ownership(state, body_bank, ref, body_ref)
        except ValueError:
            continue
        result.append({'body_ref': deepcopy(body_ref), 'points_sha256': row['record']['points_sha256'],
                       'source': deepcopy(row['record']['source']), 'association': deepcopy(row['association'])})
    return result


def retain(state, assets, face_ref, body_bank, analysis, review, *, family='skin_colour', operation_id=None):
    """Stage immutable support and its pointer only; host owns preview/confirmation."""
    kind, operation = family_spec(family, operation_id)
    out = S.check(state); body_bank = B.check(body_bank); ref, face = _face(out, face_ref)
    review = _review(review); observation = _analysis(face, analysis)
    body, face_link = _ownership(out, body_bank, ref, review['body_ref'])
    measured = body['record']
    if review['points_sha256'] != measured['points_sha256']:
        raise ValueError('Body-skin review names stale measured pose points')
    record = check_record({'version': 1, 'face_ref': ref,
        'source': {key: measured['source'][key] for key in ('sha256', 'width', 'height')},
        'row': {'target': kind, 'operation_id': operation, 'face_evidence': deepcopy(face['evidence']),
            'body_record_sha256': E.content_digest(measured),
            'body_association_revision': body_bank['association_revision'],
            'people_association_revision': out['association_revision'],
            'body_link': deepcopy(body['association']), 'face_link': deepcopy(face_link),
            'observation': observation, 'review': review,
            **({'face_skin_observation': _reference_observation(face, analysis)}
               if family == 'body_face_match' else {})}}, family=family, operation_id=operation)
    if type(assets) is not dict or len(assets) > 4096:
        raise ValueError('Invalid body-skin project support bank')
    key = content_digest(record); bank = deepcopy(assets)
    if key in bank and bank[key] != record:
        raise ValueError('Immutable body-skin asset hash collision')
    if key not in bank and len(bank) >= 4096:
        raise ValueError('Body-skin project support bank is full')
    bank[key] = record
    if len(json.dumps(bank, allow_nan=False).encode()) > 16*1024*1024:
        raise ValueError('Body-skin project support assets exceed the canonical byte budget')
    descriptor = {'owner': ref, 'content_sha256': key, 'kind': kind}
    if face['local_assets'].get(kind) != descriptor:
        face['local_assets'][kind] = descriptor; out['revision'] += 1
    return S.check(out), bank


def _attached(state, assets, ref, *, family='skin_colour', operation_id=None):
    kind, operation = family_spec(family, operation_id)
    _, face = _face(state, ref, enabled=False); descriptor = face['local_assets'].get(kind)
    if descriptor is None:
        return None
    if type(assets) is not dict:
        raise ValueError('Body-skin support bank is missing')
    key = descriptor['content_sha256']
    record = check_record(assets.get(key), family=family, operation_id=operation)
    if (content_digest(record) != key or record['face_ref'] != ref
            or descriptor != {'owner': ref, 'content_sha256': key, 'kind': kind}):
        raise ValueError('Body-skin descriptor is missing, changed or owned by another face')
    return record, key


def resolve(state, assets, face_ref, body_bank, analysis, *, family='skin_colour', operation_id=None):
    """Absent means old face-only behavior; stale attached support is an error."""
    _, operation = family_spec(family, operation_id)
    state = S.check(state); ref, _ = _face(state, face_ref, enabled=False)
    attached = _attached(state, assets, ref, family=family, operation_id=operation)
    if attached is None:
        return None
    ref, face = _face(state, ref); body_bank = B.check(body_bank)
    record, key = attached; row = record['row']; review = row['review']
    body, face_link = _ownership(state, body_bank, ref, review['body_ref'])
    if (row['face_evidence'] != face['evidence']
            or row['body_record_sha256'] != E.content_digest(body['record'])
            or review['points_sha256'] != body['record']['points_sha256']
            or row['body_association_revision'] != body_bank['association_revision']
            or row['people_association_revision'] != state['association_revision']
            or row['body_link'] != body['association'] or row['face_link'] != face_link
            or row['observation'] != _analysis(face, analysis)):
        raise ValueError('Body-skin review is stale; source/model/body/person evidence must be reviewed again')
    if (family == 'body_face_match'
            and row['face_skin_observation'] != _reference_observation(face, analysis)):
        raise ValueError('Body/face own-face reference observation changed; review again')
    return record, key


def detach(state, face_ref, *, family='skin_colour', operation_id=None):
    """Remove the active pointer even when evidence is stale; preserve history bytes."""
    kind, _ = family_spec(family, operation_id)
    out = S.check(state); _, face = _face(out, face_ref, enabled=False)
    if kind in face['local_assets']:
        del face['local_assets'][kind]; out['revision'] += 1
    return S.check(out)


def _manual(recipe, shape):
    value = M.raster(recipe, shape)
    if type(value) is not np.ndarray or value.dtype != np.uint8 or value.shape != shape:
        raise ValueError('Body-skin manual raster must be the actual Rust uint8 source coverage')
    return np.ascontiguousarray(value, dtype=np.float32) / np.float32(255)


def _protect_faces(coverage, state, source):
    """Veto every retained face, including disabled/unresolved neighbors.

    Boxes are source-normalized extents. Reserve whole intersecting pixel
    footprints plus one render-pixel guard, not merely pixel-centre samples.
    This is conservative protection, not positive facial/body segmentation.
    """
    h, w = coverage.shape; count = 0
    for face in state['faces'].values():
        if face['asset_sha256'] != source:
            continue
        left, top, right, bottom = face['box']
        x0, y0 = max(0, math.floor(left*w)-1), max(0, math.floor(top*h)-1)
        x1, y1 = min(w, math.ceil(right*w)+1), min(h, math.ceil(bottom*h)+1)
        coverage[y0:y1, x0:x1] = 0; count += 1
    return count


def raster(state, assets, face_ref, body_bank, analysis, shape, *, byte_budget=None,
           family='skin_colour', operation_id=None):
    """Return readonly target coverage and facts, never corrected pixels.

    Call only for nonneutral intent in the explicitly named family. Neutral reset
    must not require live support resolution. All attached same-source regions
    across all allowlisted families reserve ownership for OTHER faces, even
    disabled ones; sorted-effect precedence never decides it. The same face's
    deliberately authorized families may compose on separately reviewed
    coverages. None can borrow a different family's support or consent.
    """
    _, operation = family_spec(family, operation_id)
    resolved = resolve(state, assets, face_ref, body_bank, analysis,
                       family=family, operation_id=operation)
    if resolved is None:
        return None, {'enabled': False}
    state = S.check(state); record, key = resolved
    if type(shape) not in (list, tuple) or len(shape) != 2 or any(type(n) is not int or n < 2 for n in shape):
        raise ValueError('Body-skin raster needs a whole-source render extent')
    shape = tuple(shape)
    E.whole_source_shape({**record['source'], 'orientation': E.ORIENTATION}, shape)
    SEM.check_analysis_fields(analysis, shape)
    excluded = None
    if family in ('body_skin_evenness', 'body_face_match'):
        # One admission field for both the real solver and the review overlay.
        # This is known-occluder protection, not complete instance segmentation.
        excluded = analysis.get('excluded')
        if (type(excluded) is not np.ndarray or excluded.dtype != np.float32
                or excluded.shape != shape or not np.isfinite(excluded).all()
                or np.any(excluded < 0) or np.any(excluded > 1)):
            raise ValueError('Body chroma correction needs actual finite float32 known-occluder support')
    others = []
    for face in state['faces'].values():
        ref = S.face_ref(face)
        if ref == record['face_ref'] or ref['asset_sha256'] != record['source']['sha256']:
            continue
        for other_family in FAMILIES:
            attached = _attached(state, assets, ref, family=other_family)
            if attached is not None:
                other, _ = attached
                if other['source'] != record['source']:
                    raise ValueError('Competing body-skin review has different source dimensions')
                others.append(other)
    recipes = [record['row']['review']['recipe']] + [r['row']['review']['recipe'] for r in others]
    work = sum(M.validate_budget(recipe, shape)['work'] for recipe in recipes)
    if work > M.MAX_WORK:
        raise ValueError('All body-skin review rasters exceed the aggregate work budget')
    if byte_budget is None:
        from .cpu_memory_budget import available_estimate
        byte_budget = available_estimate()
    # One coverage, one sequential competing region, masks and bounded raster
    # transport/validation scratch. This is admission, not measured peak memory.
    needed = shape[0]*shape[1]*24 + 32*1024*1024
    if type(byte_budget) is not int or byte_budget < needed:
        raise ValueError('Body-skin coverage exceeds memory budget before raster allocation')
    coverage = _manual(recipes[0], shape)
    coverage *= analysis['body_skin']
    if excluded is not None:
        coverage[excluded > .1] = 0
    protected = _protect_faces(coverage, state, record['source']['sha256'])
    for other in others:
        competing = _manual(other['row']['review']['recipe'], shape)
        # Current semantic support is the same whole-source class, not a claimed
        # other-person mask. Refuse even one positive competing footprint.
        if np.any((coverage > 0) & (competing > 0)):
            raise ValueError('Reviewed body-skin regions overlap another attached owner; revise the manual regions')
    if not np.any(coverage > 0):
        raise ValueError('Reviewed body-skin region contains no admitted visible semantic skin')
    coverage = np.ascontiguousarray(coverage, dtype=np.float32); coverage.setflags(write=False)
    row = record['row']
    return coverage, {'enabled': True, 'body_ref': deepcopy(row['review']['body_ref']),
        'face_ref': deepcopy(record['face_ref']), 'source': deepcopy(record['source']),
        'support_sha256': key, 'body_record_sha256': row['body_record_sha256'],
        'points_sha256': row['review']['points_sha256'],
        'person_id': row['body_link']['person_id'],
        'body_association_revision': row['body_association_revision'],
        'people_association_revision': row['people_association_revision'],
        'semantic_observation': deepcopy(row['observation']),
        'scope': 'reviewed-body-skin-not-instance-segmentation',
        'support': 'whole-photo-body-skin-edit-weight-intersected-explicit-manual-region',
        'manual_coordinates': 'source-normalized-pixel-edges',
        'protected_face_boxes': protected, 'competing_review_count': len(others),
        'overlap_policy': 'refuse-positive-competing-manual-coverage',
        'support_pixels': int(np.count_nonzero(coverage > 0)),
        'semantic_resolution': 'producer-grid-preserved-no-new-full-resolution-inference',
        'occlusion': 'explicit-review-and-six-class-semantics-not-complete-occluder-segmentation',
        'manual_rasterizer': 'existing-rust-local-mask', 'runtime_quality_accepted': False}


def validate_project(project, *, family='skin_colour', operation_id=None):
    """Resolve historical descriptor bytes, not historical links against live state."""
    kind, operation = family_spec(family, operation_id)
    def visit(value, assets):
        if isinstance(value, dict):
            # Private documents/virtual copies own independent support stores.
            # Never resolve their descriptors through the enclosing live owner.
            if 'people_support_assets' in value:
                assets = value['people_support_assets']
                if type(assets) is not dict:
                    raise ValueError('Historical body-skin support bank is invalid')
            if 'face_instance_id' in value and kind in value.get('local_assets', {}):
                ref = S.check_ref({k: value[k] for k in ('asset_sha256', 'face_instance_id', 'analysis_revision')})
                descriptor = value['local_assets'][kind]
                if (type(descriptor) is not dict or set(descriptor) != {'owner', 'content_sha256', 'kind'}
                        or descriptor['owner'] != ref or descriptor['kind'] != kind):
                    raise ValueError('Historical body-skin descriptor ownership changed')
                key = S.digest(descriptor['content_sha256'])
                record = check_record(assets.get(key), family=family, operation_id=operation)
                if (record['face_ref'] != ref or content_digest(record) != key
                        or record['row']['face_evidence'] != value.get('evidence')):
                    raise ValueError('Historical body-skin support is missing or changed')
            for child in value.values():
                visit(child, assets)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child, assets)
    visit(project, {})
