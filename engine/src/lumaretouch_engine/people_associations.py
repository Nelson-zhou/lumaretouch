"""Explicit graph mutations; caller commits returned state with existing receipts."""
from copy import deepcopy
from . import people_state as S


def set_link(state, face_id, person_id, status, *, user_confirmed=False):
    out = S.check(state)
    if face_id not in out['faces'] or person_id not in out['persons'] or status not in S.LINK_STATES:
        raise ValueError('Unknown face, person or association status')
    if type(user_confirmed) is not bool: raise ValueError('Confirmation must be an explicit boolean')
    if status == 'confirmed' and user_confirmed is not True:
        raise ValueError('Candidate similarity is not user confirmation')
    out['association_revision'] += 1; out['revision'] += 1
    # Unlink preserves person overrides and all face edit history.
    for link in out['links']:
        if link['face_instance_id'] == face_id and link['state'] == 'confirmed' and status == 'confirmed':
            link['state'] = 'unresolved'
    out['links'] = [x for x in out['links'] if (x['face_instance_id'], x['person_id']) != (face_id, person_id)]
    out['links'].append({'face_instance_id': face_id, 'person_id': person_id,
                         'state': status, 'confirmation_revision': out['association_revision'] if user_confirmed else None})
    return S.check(out)


def set_face_status(state, face_id, *, enabled=None, labels=None):
    out = S.check(state)
    if face_id not in out['faces']: raise ValueError('Unknown face instance')
    face = out['faces'][face_id]
    if enabled is not None: face['enabled'] = enabled
    if labels is not None: face['labels'] = deepcopy(labels)
    out['revision'] += 1
    return S.check(out)


def reanalyse(state, asset_sha256, replacements, *, expected_revision, user_confirmed=False):
    """Caller supplies explicit stable-ID bindings, never nearest/order matching.

    Existing approved local support makes replacement a refusal. A future migration
    must archive those assets separately and obtain review, not erase or rebind them.
    Omitted faces retain old analysis; a new detection gets a new ID via add_faces.
    """
    out = S.check(state)
    if not user_confirmed or expected_revision != out['revision']:
        raise ValueError('Reanalysis requires explicit review of the current graph')
    S.digest(asset_sha256)
    if type(replacements) is not dict or not replacements: raise ValueError('Explicit replacement map required')
    for face_id, evidence in replacements.items():
        face = out['faces'].get(face_id)
        if face is None or face['asset_sha256'] != asset_sha256: raise ValueError('Reanalysis source mismatch')
        if face['local_assets']: raise ValueError('Approved local support must be preserved before reanalysis')
        face['evidence'] = S.check_evidence(evidence)
        face['analysis_revision'] += 1
    out['revision'] += 1
    # Revision pins force all stale rendering/transfer references to be reviewed.
    return S.check(out)


def add_faces(state, asset_sha256, faces, *, detector_limit, limit_reached):
    """Add explicit fresh instances; detector cap means an incomplete census."""
    out = S.check(state); S.digest(asset_sha256)
    if type(detector_limit) is not int or not 1 <= detector_limit <= S.MAX_FACES or type(limit_reached) is not bool:
        raise ValueError('Detection budget and truncation must be explicit')
    if len(faces) > detector_limit: raise ValueError('Detector exceeded its admitted budget')
    for face in faces:
        if face['asset_sha256'] != asset_sha256 or face['face_instance_id'] in out['faces']:
            raise ValueError('Fresh detections cannot overwrite retained instances')
        out['faces'][face['face_instance_id']] = deepcopy(face)
    out['analysis_runs'][asset_sha256] = {'detector_limit': detector_limit,
        'limit_reached': limit_reached, 'census_complete': False,
        'notice': 'Detection limit reached; more faces may be present' if limit_reached else 'Detection is not proof that every face was found'}
    out['revision'] += 1
    return S.check(out)


def create_person(state):
    """Create an anonymous container only; no face is associated automatically."""
    import uuid
    out = S.check(state); key = uuid.uuid4().hex
    out['persons'][key] = {'anonymous': True}; out['revision'] += 1
    return S.check(out), key


def set_group(state, group_id, *, label, priority, face_ids):
    """User-defined labels and explicit precedence, never inferred demographics."""
    out = S.check(state); S.token(group_id)
    out['association_revision'] += 1
    out['groups'][group_id] = {'label': label, 'priority': priority, 'face_ids': list(face_ids)}
    out['revision'] += 1
    return S.check(out)


def confirmed_targets(state, person_id):
    """Exact candidate list for review; rejected/unresolved links never qualify."""
    state = S.check(state)
    if person_id not in state['persons']: raise ValueError('Unknown anonymous person')
    return [S.face_ref(state['faces'][x['face_instance_id']]) for x in state['links']
            if x['person_id'] == person_id and x['state'] == 'confirmed'
            and state['faces'][x['face_instance_id']]['enabled']]
