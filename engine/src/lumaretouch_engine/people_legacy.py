"""Lossless legacy-intent archive and explicit reviewed binding.

Never guess from box proximity, detector order or currently selected face. The
caller retains original project/history records and source-owned asset storage.
No masks, arrays or history records are destroyed or attached to a new person.
"""
from copy import deepcopy
import uuid
from . import people_state as S


def archive(state, *, legacy_key, serialized_intent, asset_sha256, owner_evidence=None, history_ref=None):
    """Archive ambiguous old deform/recipe/recovery references before migration.

    serialized_intent must be JSON data; binary mask bytes stay at history_ref.
    An old landmark owner hash is evidence for review, not a stable instance ID.
    """
    out = S.check(state); S.token(legacy_key); S.digest(asset_sha256)
    out['unresolved_legacy'].append({'id': uuid.uuid4().hex, 'legacy_key': legacy_key,
        'asset_sha256': asset_sha256, 'intent': deepcopy(serialized_intent),
        'owner_evidence': deepcopy(owner_evidence), 'history_ref': deepcopy(history_ref),
        'status': 'unresolved', 'binding': None})
    out['revision'] += 1
    return S.check(out)


def bind_parameters(state, archive_id, face_ref, leaves, *, expected_revision, user_confirmed=False):
    """Bind reviewed portable leaves; archive remains even after confirmation.

    leaves are registry-validated {operation_id,parameter_path,value} records.
    Recovery assets cannot use this path; they require original-source ownership.
    """
    out = S.check(state)
    if user_confirmed is not True or expected_revision != out['revision']: raise ValueError('Legacy binding needs current explicit review')
    ref = S.check_ref(face_ref); face = out['faces'].get(ref['face_instance_id'])
    if face is None or S.face_ref(face) != ref: raise ValueError('Legacy binding face changed')
    record = next((x for x in out['unresolved_legacy'] if x['id'] == archive_id), None)
    if record is None or record['status'] != 'unresolved' or record['asset_sha256'] != ref['asset_sha256']:
        raise ValueError('Legacy intent cannot be rebound or moved to another source')
    if type(leaves) is not list or not leaves: raise ValueError('Reviewed parameter leaves required')
    for leaf in leaves:
        if type(leaf) is not dict or set(leaf) != {'operation_id', 'parameter_path', 'value'}: raise ValueError('Only portable leaves may migrate')
        out = S.set_override(out, 'face', ref['face_instance_id'], leaf['operation_id'], leaf['parameter_path'], leaf['value'])
    record = next(x for x in out['unresolved_legacy'] if x['id'] == archive_id)
    record['status'] = 'confirmed'; record['binding'] = ref
    out['revision'] += 1
    return S.check(out)
