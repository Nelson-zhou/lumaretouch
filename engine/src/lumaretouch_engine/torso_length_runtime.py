# SPDX-License-Identifier: GPL-3.0-or-later
"""All-or-nothing torso admission on the canonical source and body/person graph."""
from copy import deepcopy
import numpy as np
from . import torso_length_state as S, body_pose_state as B, body_pose_evidence as E
from .torso_length_field import TorsoLengthField

FACE_BINDING_KEYS = ('associated_face_ref', 'associated_face_box',
                     'associated_face_evidence_sha256')


class TorsoLengthRefused(ValueError):
    def __init__(self, refusals):
        self.refusals = refusals
        super().__init__('Torso length request refused: '+'; '.join(row['reason'] for row in refusals))


def _observed(point):
    return (point['visibility'] >= .8 and point['presence'] >= .8
            and 0 < point['x'] < 1 and 0 < point['y'] < 1)


def _overlap(a, b):
    # Boundary contact is ambiguous ownership too; never turn equality into a
    # loophole for a touching foreign face or body.
    return bool(np.all(a[0] <= b[1]) and np.all(b[0] <= a[1]))


def _rectangle(box, shape):
    h, w = shape
    value = np.asarray(box, np.float64).reshape(2, 2)*np.array([w-1, h-1])
    return value[0], value[1]


def _body_box(record, shape):
    h, w = shape
    points = np.array([[p['x']*(w-1), p['y']*(h-1)]
                       for p in record['points'] if _observed(p)], np.float64)
    # An unresolved retained body cannot be assumed absent or safely outside.
    if len(points) < 2:
        raise ValueError('Another retained body lacks enough observed bounds to prove clear torso ownership')
    return points.min(axis=0), points.max(axis=0)


def associated_face(row, people_state):
    """Resolve only a current explicitly confirmed person, never nearest face."""
    from . import people_state as P
    people = P.check(people_state)
    source = E.source(row['record']['source'])
    link = row['association']
    if (link is None or link['person_id'] not in people['persons']
            or link['body_ref'] != row['record']['body_ref']
            or link['people_association_revision'] != people['association_revision']):
        raise ValueError('Torso length requires current explicit same-person body/face ownership')
    faces = [people['faces'][item['face_instance_id']] for item in people['links']
             if item['person_id'] == link['person_id'] and item['state'] == 'confirmed'
             and people['faces'][item['face_instance_id']]['asset_sha256'] == source['sha256']]
    if len(faces) != 1:
        raise ValueError('Torso length needs exactly one confirmed source face for this body person')
    face = faces[0]
    evidence = face['evidence']
    if face['manual'] or evidence['status'] != 'verified':
        raise ValueError('Torso length requires an actual verified associated face observation, not a manual or unresolved box')
    if (evidence['source_width'] != source['width'] or evidence['source_height'] != source['height']
            or evidence['orientation'] != source['orientation']):
        raise ValueError('Associated face observation does not belong to this exact canonical source frame')
    return deepcopy(face)


def face_binding(face):
    from .people_state import face_ref
    return dict(zip(FACE_BINDING_KEYS, (face_ref(face), deepcopy(face['box']),
                                       E.content_digest(face['evidence']))))


def bind_support_review(data, row, people_state):
    """Attach factual current identity to an explicitly reviewed source region.

    UI supplies actual manually reviewed geometry and confirmations. Identity
    metadata comes only from the canonical confirmed graph. A caller that also
    supplies metadata must supply all three fields and match them exactly.
    """
    if type(data) is not dict:
        raise ValueError('Torso length review data must be an object')
    binding = face_binding(associated_face(row, people_state))
    supplied = set(data).intersection(FACE_BINDING_KEYS)
    if supplied and (supplied != set(FACE_BINDING_KEYS)
                     or any(data[key] != value for key, value in binding.items())):
        raise ValueError('Torso length review names an outdated or different associated face')
    return S.policy_check_support({**deepcopy(data), **binding}, row['record'])


def validate_face_review(data, row, people_state):
    """No rebind on render/transfer: changed face evidence needs another review."""
    face = associated_face(row, people_state)
    if any(data.get(key) != value for key, value in face_binding(face).items()):
        raise ValueError('Torso length reviewed face analysis, box or evidence changed; review the source again')
    head = data['head_box']
    box = face['box']
    if not (head[0] < box[0] < box[2] < head[2]
            and head[1] < box[1] < box[3] < head[3]):
        raise ValueError('Whole associated face must lie strictly inside the reviewed complete head/hair box')
    return face


def prepare_fields(state, asset_sha256, shape, *, people_state=None, byte_budget,
                   operation_policies=None, source_pixels=None, source_frame=None):
    policies = {**(operation_policies or {}), **S.policies()}
    state = B.check(state, operation_policies=policies)
    E.digest(asset_sha256)
    if type(byte_budget) is not int or byte_budget < 1024*1024:
        raise ValueError('Torso length field memory budget is missing')
    if source_frame is None:
        raise ValueError('Torso length preparation needs the exact canonical source frame')
    source = E.source(source_frame)
    E.whole_source_shape(source, shape)
    rows = [row for row in state['bodies'].values()
            if row['record']['source']['sha256'] == asset_sha256]
    if source['sha256'] != asset_sha256 or any(row['record']['source'] != source for row in rows):
        raise ValueError('Torso length records differ from current source dimensions, orientation or digest')
    active = [row for row in rows if row['enabled'] and S.OPERATION_ID in row['operations']
              and row['operations'][S.OPERATION_ID]['enabled']
              and S.active(row['operations'][S.OPERATION_ID]['recipe'])]
    if len(active) > 8:
        raise ValueError('Torso length active-body budget exceeded; no silent truncation')
    people = None
    if people_state is not None:
        from .people_state import check
        people = check(people_state)
    fields, failures = [], []
    for row in active:
        ref = row['record']['body_ref']
        try:
            if people is None:
                raise ValueError('Torso length requires the canonical people graph and an explicitly reviewed own face')
            asset = B.support(state, ref, S.OPERATION_ID)
            if asset is None:
                raise ValueError('Torso length requires independently reviewed whole upper-body support')
            face = validate_face_review(asset['data'], row, people)
            field = TorsoLengthField(row, asset, shape)
            field.associated_face_id = face['face_instance_id']
            envelope = field.envelope()
            face_box = _rectangle(face['box'], shape)
            if not (np.all(field.plateau_bounds[0] < face_box[0])
                    and np.all(face_box[1] < field.plateau_bounds[1])):
                raise ValueError('Complete associated face must stay inside the rigid upper translation plateau')
            for other in rows:
                if other['record']['body_ref'] == ref:
                    continue
                if _overlap(envelope, _body_box(other['record'], shape)):
                    raise ValueError('Torso length transition touches another observed body; ownership is ambiguous')
            for other in people['faces'].values():
                if other['asset_sha256'] != asset_sha256 or other['face_instance_id'] == face['face_instance_id']:
                    continue
                evidence = other['evidence']
                if (evidence['source_width'] != source['width']
                        or evidence['source_height'] != source['height']
                        or evidence['orientation'] != source['orientation']):
                    raise ValueError('A retained foreign face has uncertain source bounds; torso ownership cannot be proved')
                # Disabled, unresolved, manual and unassociated faces still own
                # pixels. None can be excluded from boundary protection.
                if _overlap(envelope, _rectangle(other['box'], shape)):
                    raise ValueError('Torso length transition touches another retained face')
            field.facts.update(associated_face_ref=deepcopy(asset['data']['associated_face_ref']),
                               associated_face_evidence_sha256=asset['data']['associated_face_evidence_sha256'])
            fields.append(field)
        except (ValueError, RuntimeError, OSError) as error:
            failures.append({'body_ref': deepcopy(ref), 'operation_id': S.OPERATION_ID,
                             'reason': str(error), 'requested_recipe': deepcopy(row['operations'][S.OPERATION_ID]['recipe']),
                             'applied': False})
    if failures:
        raise TorsoLengthRefused(failures)
    if sum(field.resident_bytes() for field in fields) > byte_budget:
        raise ValueError('Retained torso length fields exceed the admitted memory budget')
    return tuple(fields)
