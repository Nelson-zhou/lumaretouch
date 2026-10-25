"""Exact neutral-original census proof for the private edited-capture strategy.

This is not a renderer or a generic export fast path. A candidate result only
selects a strategy; the definitive proof must still run on the original decode.
No snapshot, recipe, FaceRef, source pixel or retained array is changed.
AUTHORED / UNRUN: static inspection is not numerical or memory acceptance.
"""
import hashlib

import numpy as np

from . import people_algorithms as A, people_state as S
from . import people_render_plan as P, people_resolver as R


_CONTEXT_FIELDS = frozenset(('path', 'file_stamp', 'asset_sha256', 'document_id'))
_SNAPSHOT_FIELDS = frozenset((
    'state', 'asset_sha256', 'analyses', 'document_id', 'support_assets',
    'creative_source', 'hair_colour_assets', 'hair_unification_assets', 'hair_colour_evidence',
    'hair_colour_source_path', 'hair_colour_source_stamp',
))
_ANALYSIS_REQUIRED = frozenset(('face_ref', 'evidence', 'landmarks', 'excluded', 'skin'))
_ANALYSIS_FIELDS = _ANALYSIS_REQUIRED | frozenset((
    'face_skin', 'face_skin_observation', 'body_skin', 'body_skin_observation',
))


def _context(spec):
    value = getattr(spec, '_creative_capture_original_source', None)
    if value is None:
        return None
    if type(value) is not dict or set(value) != _CONTEXT_FIELDS:
        raise ValueError('Neutral census requires the exact private original-source context')
    path, stamp = value['path'], value['file_stamp']
    if type(path) is not str or not path or '\x00' in path:
        raise ValueError('Neutral census original path is invalid')
    if (type(stamp) not in (list, tuple) or len(stamp) != 5
            or any(type(n) is not int for n in stamp)):
        raise ValueError('Neutral census requires the original decode file stamp')
    S.digest(value['asset_sha256'])
    S.token(value['document_id'])
    if value['document_id'] != getattr(spec, 'people_document_id', None):
        raise ValueError('Neutral census context belongs to another document')
    return value


def _verify_file(context):
    from .local_mask_state import file_stamp, source_digest
    before = file_stamp(context['path'])
    if before != tuple(context['file_stamp']):
        raise ValueError('Neutral census source changed since original decoding')
    if source_digest(context['path']) != context['asset_sha256']:
        raise ValueError('Neutral census source bytes differ from the captured asset')
    if file_stamp(context['path']) != before:
        raise ValueError('Neutral census source changed during verification')


def _analysis(face, raw, source_shape):
    """Validate all actual planes before declining an ambiguous producer grid."""
    from .skin_colour_support import check_analysis_fields as check_face_skin
    from .body_skin_semantics import check_analysis_fields as check_body_skin
    from .people_render_runtime import verify_analysis

    if (type(raw) is not dict or not _ANALYSIS_REQUIRED.issubset(raw)
            or set(raw) - _ANALYSIS_FIELDS):
        raise ValueError('Neutral census analysis fields are incomplete or unknown')
    if S.check_ref(raw['face_ref']) != S.face_ref(face) or raw['evidence'] != face['evidence']:
        raise ValueError('Neutral census analysis owner or revision is stale')
    evidence = S.check_evidence(raw['evidence'])
    if evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe':
        raise ValueError('Neutral census supplied analysis is not verified detector evidence')
    # Bound the only numeric conversion before allocating; never convert RGB.
    landmarks = raw['landmarks']
    if (type(landmarks) is not np.ndarray or landmarks.shape != (478, 3)
            or landmarks.dtype.kind not in 'uif'):
        raise ValueError('Neutral census landmark record is invalid')
    try:
        points = np.asarray(landmarks, dtype='<f4')
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError('Neutral census landmark record is invalid') from error
    if not np.isfinite(points).all():
        raise ValueError('Neutral census landmark record is invalid')
    if hashlib.sha256(np.ascontiguousarray(points).tobytes()).hexdigest() != evidence['landmark_digest']:
        raise ValueError('Neutral census measured landmark bytes changed')

    shapes = set()
    for name in ('excluded', 'skin', 'face_skin', 'body_skin'):
        plane = raw.get(name)
        if plane is None:
            continue
        if (type(plane) is not np.ndarray or plane.ndim != 2 or not plane.size
                or plane.dtype.kind not in 'uif' or not np.isfinite(plane).all()
                or np.any((plane < 0) | (plane > 1))):
            raise ValueError('Neutral census contains invalid retained semantic coverage')
        if evidence['semantic_model_sha256'] is None:
            raise ValueError('Neutral census semantic coverage lacks loaded-model evidence')
        shapes.add(tuple(plane.shape))
    producer_grid = True
    for name, observation in (('face_skin', check_face_skin(raw)), ('body_skin', check_body_skin(raw))):
        if observation is not None:
            producer_grid &= raw[name].shape == (observation['producer_height'], observation['producer_width'])
    # Legacy excluded/skin have no independent producer metadata. Their actual
    # common retained grid is the strongest existing transport evidence.
    if len(shapes) > 1:
        return False
    verify_analysis(face, raw, next(iter(shapes), tuple(source_shape)))
    return producer_grid


def _exact_recipes(state, asset):
    """Do not hide disabled, shadowed, dormant or bool/numeric-aliased intent."""
    defaults, specifications = A.defaults(), A.specifications()
    neutral = True
    photo_operations = {}
    for row in state['overrides']:
        op, path, value = row['operation_id'], row['parameter_path'], row['value']
        if op not in defaults or path not in defaults[op]:
            raise ValueError('Neutral census contains an unknown operation or parameter')
        expected = defaults[op][path]
        allowed = (type(value) in (int, float) if type(expected) in (int, float)
                   else type(value) is type(expected))
        if not allowed:
            raise ValueError('Neutral census parameter has a noncanonical scalar domain')
        neutral &= value == expected
        if row['scope'] == 'all_people' and row['target_id'] == asset:
            photo_operations.setdefault(op, {})[path] = {'value': value}
    face_ids = [key for key, face in state['faces'].items() if face['asset_sha256'] == asset]
    # Materialize zero-face photograph intent without fabricating a FaceRef.
    resolved_rows = ((R.resolve(state, key, defaults) for key in face_ids) if face_ids
                     else ({'operations': photo_operations, 'conflicts': []},))
    for resolved in resolved_rows:
        values = A.recipes(resolved)
        A.validate_compatibility(values)
        if any(value != specifications[operation][0] for operation, value in values.items()):
            neutral = False
    return neutral


def _snapshot_state(snapshot, document_id):
    from .people_document_owner import validate_snapshot
    from .people_support_assets import check_store
    from .hair_colour_assets import check_store as check_hair_store
    from .eye_makeup_enhance_project import validate_graph as validate_eye_makeup

    if (type(snapshot) is not dict
            or not {'state', 'asset_sha256', 'analyses', 'document_id'}.issubset(snapshot)):
        raise ValueError('Neutral census snapshot is missing its owner or retained bank')
    validate_snapshot(snapshot, document_id)
    state = S.check(snapshot['state'])
    asset = S.digest(snapshot['asset_sha256'])
    A.FACE_DECORATION.validate_graph(state)
    A.FACIAL_SCULPT.validate_graph(state)
    validate_eye_makeup(state)
    supports = check_store(snapshot.get('support_assets', {}))
    from .hair_volume_project import validate_owned_graph as validate_volume
    validate_volume(state, supports)
    hair = check_hair_store(snapshot.get('hair_colour_assets', {}))
    from .hair_unification_assets import verify_graph as verify_unification
    verify_unification(state, snapshot.get('hair_unification_assets', {}), hair)
    if type(snapshot['analyses']) is not dict or len(snapshot['analyses']) > S.MAX_FACES:
        raise ValueError('Neutral census analysis bank is invalid or oversized')
    return state, asset, supports, hair


def _plain_metadata(snapshot, state, asset, supports, hair):
    return not (
        set(snapshot) - _SNAPSHOT_FIELDS or supports or hair or snapshot.get('hair_unification_assets')
        or snapshot.get('creative_source') is not None
        or state['persons'] or state['groups'] or state['links'] or state['unresolved_legacy']
        or any(face['local_assets'] or face['asset_sha256'] != asset for face in state['faces'].values())
        or set(state['analysis_runs']) - {asset}
        or any(row['scope'] == 'all_people' and row['target_id'] != asset for row in state['overrides'])
        or snapshot.get('hair_colour_evidence') is not None
        or snapshot.get('hair_colour_source_stamp') is not None
    )


def _retained_bank(snapshot, state, asset, source_shape=None):
    """Check all supplied rows, not only enabled faces needed by the planner."""
    neutral = True
    bank, extents = snapshot['analyses'], set()
    for face in state['faces'].values():
        if face['asset_sha256'] != asset:
            neutral = False
            continue
        evidence = face['evidence']
        extent = (evidence['source_height'], evidence['source_width'])
        extents.add(extent)
        if source_shape is not None and extent != tuple(source_shape):
            raise ValueError('Neutral census evidence belongs to another original extent')
        if (face['manual'] or evidence['status'] != 'verified'
                or evidence['backend'] != 'mediapipe' or face['face_instance_id'] not in bank):
            neutral = False
    if len(extents) > 1:
        raise ValueError('Neutral census has conflicting retained original extents')
    for key, raw in bank.items():
        face = state['faces'].get(key)
        if face is None or face['asset_sha256'] != asset:
            raise ValueError('Neutral census contains a foreign analysis entry')
        evidence = face['evidence']
        shape = source_shape if source_shape is not None else (evidence['source_height'], evidence['source_width'])
        neutral &= _analysis(face, raw, shape)
    return neutral


def neutral_census_candidate(snapshot):
    """Pre-decode selection only. True never authorizes skipping preparation.

    The caller must admit retained-input/validation scratch BEFORE this call and
    still run neutral_original_census against a separately owned true decode.
    """
    if snapshot is None:
        return False
    if type(snapshot) is not dict:
        raise ValueError('Neutral census candidate is not a frozen snapshot')
    if snapshot.get('creative_source') is not None:
        return False
    document_id = snapshot.get('document_id')
    if document_id is None:
        return False
    S.token(document_id)
    state, asset, supports, hair = _snapshot_state(snapshot, document_id)
    neutral = _plain_metadata(snapshot, state, asset, supports, hair)
    neutral &= _exact_recipes(state, asset)
    neutral &= _retained_bank(snapshot, state, asset)
    return neutral


def neutral_original_census(spec, source):
    """Prove an exact-default original census without target-grid preparation.

    Missing context/unsupported retained inputs return False; invalid supplied
    original evidence raises. False is NOT permission to erase the people bank.
    Once private capture was selected, its owner must refuse a failed proof,
    rather than silently fall through to an unadmitted full preparation path.

    The caller proves the true decoder/pixels relationship, supplies no repaired
    source, and rechecks actual document/file fences at final publication.
    """
    snapshot = getattr(spec, 'people', None)
    if snapshot is None:
        return False
    context = _context(spec)
    if context is None:
        return False
    if type(snapshot) is not dict:
        raise ValueError('Neutral census needs an actual frozen people snapshot')
    if getattr(spec, 'creative_base', None) is not None or snapshot.get('creative_source') is not None:
        return False
    if (type(source) is not np.ndarray or source.ndim != 3
            or source.shape[2] != 3 or min(source.shape[:2]) < 1):
        raise ValueError('Neutral census requires actual nonempty original RGB pixels')
    if source.dtype not in (np.uint8, np.uint16):
        return False
    from .effect_recovery_state import check as check_recovery

    state, asset, supports, hair = _snapshot_state(snapshot, spec.people_document_id)
    if asset != context['asset_sha256']:
        raise ValueError('Neutral census graph belongs to another original source')
    _verify_file(context)
    recovery = check_recovery(getattr(spec, 'effect_recovery', None))
    eligible = _plain_metadata(snapshot, state, asset, supports, hair)
    eligible &= _retained_bank(snapshot, state, asset, source.shape[:2])
    eligible &= _exact_recipes(state, asset)
    if recovery['targets'] or getattr(spec, 'repair', ()):
        eligible = False
    # Existing export_prepare writes this exact neutral representation before
    # people preparation. Accept no nonempty fields or alternate containers.
    recovery_fields = getattr(spec, 'effect_recovery_fields', None)
    if recovery_fields is not None and (type(recovery_fields) is not list or recovery_fields):
        eligible = False
    for field in ('body_pose', 'body_pose_source_path', 'body_pose_source_stamp',
                  'body_pose_source_proof', 'effect_recovery_path', 'effect_recovery_stamp'):
        if getattr(spec, field, None) is not None:
            eligible = False
    hair_path = snapshot.get('hair_colour_source_path')
    if hair_path is not None and hair_path != context['path']:
        raise ValueError('Neutral census hair snapshot names another source path')
    if not eligible:
        return False

    from .people_export import fastpath_blocker
    if fastpath_blocker(snapshot):
        return False
    evidence = {key: {'face_ref': raw['face_ref'], 'evidence': raw['evidence']}
                for key, raw in snapshot['analyses'].items()}
    plan = P.build(state, asset, A.defaults(), max_faces=32, per_face_cost=1,
                   total_budget=32, available_evidence=evidence,
                   operation_check=lambda _face, _resolved: [])
    P.assert_current(plan, state)
    if any(entry['status'] != 'ready' or entry['requires_analysis'] for entry in plan['entries']):
        return False
    _verify_file(context)
    return True
