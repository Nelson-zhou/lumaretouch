# SPDX-License-Identifier: GPL-3.0-or-later
"""All-or-nothing whole-person width admission on the canonical source and body/person graph."""
from copy import deepcopy
from . import body_slim_state as S, body_pose_state as B, body_pose_evidence as E
from .body_slim_field import BodySlimField

FACE_BINDING_KEYS = ('associated_face_ref', 'associated_face_box',
                     'associated_face_evidence_sha256')


class BodySlimRefused(ValueError):
    def __init__(self, refusals):
        self.refusals = refusals
        super().__init__('Whole-body width request refused: '+'; '.join(row['reason'] for row in refusals))


def associated_face(row, people_state):
    """Resolve only a current explicitly confirmed person, never nearest face."""
    from . import people_state as P
    people = P.check(people_state)
    source = E.source(row['record']['source'])
    link = row['association']
    if (link is None or link['person_id'] not in people['persons']
            or link['body_ref'] != row['record']['body_ref']
            or link['people_association_revision'] != people['association_revision']):
        raise ValueError('Whole-body width requires current explicit same-person body/face ownership')
    faces = [people['faces'][item['face_instance_id']] for item in people['links']
             if item['person_id'] == link['person_id'] and item['state'] == 'confirmed'
             and people['faces'][item['face_instance_id']]['asset_sha256'] == source['sha256']]
    if len(faces) != 1:
        raise ValueError('Whole-body width needs exactly one confirmed source face for this body person')
    face = faces[0]
    evidence = face['evidence']
    if face['manual'] or evidence['status'] != 'verified':
        raise ValueError('Whole-body width requires an actual verified associated face observation, not a manual or unresolved box')
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
        raise ValueError('Whole-body width review data must be an object')
    binding = face_binding(associated_face(row, people_state))
    supplied = set(data).intersection(FACE_BINDING_KEYS)
    if supplied and (supplied != set(FACE_BINDING_KEYS)
                     or any(data[key] != value for key, value in binding.items())):
        raise ValueError('Whole-body width review names an outdated or different associated face')
    return S.policy_check_support({**deepcopy(data), **binding}, row['record'])


def validate_face_review(data, row, people_state):
    """No rebind on render/transfer: changed face evidence needs another review."""
    face = associated_face(row, people_state)
    if any(data.get(key) != value for key, value in face_binding(face).items()):
        raise ValueError('Whole-body width reviewed face analysis, box or evidence changed; review the source again')
    S.policy_check_support(data, row['record'])
    return face


def prepare_fields(state, asset_sha256, shape, *, people_state=None, byte_budget,
                   operation_policies=None, source_pixels=None, source_frame=None):
    policies = {**(operation_policies or {}), **S.policies()}
    state = B.check(state, operation_policies=policies)
    E.digest(asset_sha256)
    # An additive neutral family must not impose a new budget/source-shape gate
    # on old recipes. The common body owner still validates its own source.
    if not any(row['record']['source']['sha256']==asset_sha256 and row['enabled']
               and (item:=row['operations'].get(S.OPERATION_ID)) is not None
               and item['enabled'] and S.active(item['recipe'])
               for row in state['bodies'].values()):
        return ()
    if type(byte_budget) is not int or byte_budget < 1024*1024:
        raise ValueError('Whole-body width field memory budget is missing')
    if source_frame is None:
        raise ValueError('Whole-body width preparation needs the exact canonical source frame')
    source = E.source(source_frame)
    E.whole_source_shape(source, shape)
    rows = [row for row in state['bodies'].values()
            if row['record']['source']['sha256'] == asset_sha256]
    if source['sha256'] != asset_sha256 or any(row['record']['source'] != source for row in rows):
        raise ValueError('Whole-body width records differ from current source dimensions, orientation or digest')
    active = [row for row in rows if row['enabled'] and S.OPERATION_ID in row['operations']
              and row['operations'][S.OPERATION_ID]['enabled']
              and S.active(row['operations'][S.OPERATION_ID]['recipe'])]
    if len(active) > 1:
        raise ValueError('Whole-body width single-person active-body budget exceeded; no silent truncation')
    people = None
    if people_state is not None:
        from .people_state import check
        people = check(people_state)
    fields, failures = [], []
    for row in active:
        ref = row['record']['body_ref']
        try:
            if people is None:
                raise ValueError('Whole-body width requires the canonical people graph and an explicitly reviewed own face')
            asset = B.support(state, ref, S.OPERATION_ID)
            if asset is None:
                raise ValueError('Whole-body width requires independently reviewed whole-person silhouette and collar support')
            face = validate_face_review(asset['data'], row, people)
            # Pose-joint bounds are NOT a full instance silhouette. This v1
            # refuses all multi-person sources rather than trusting such bounds.
            # Disabled/unresolved bodies and faces still own image pixels.
            if len(rows) != 1:
                raise ValueError('Whole-body width v1 is single-person only; other retained bodies need independent complete ownership support')
            for other in people['faces'].values():
                if other['asset_sha256'] == asset_sha256 and other['face_instance_id'] != face['face_instance_id']:
                    raise ValueError('Whole-body width v1 refuses another retained face, including disabled or unresolved people')
            run = state['analysis_runs'].get(asset_sha256)
            if run is None or run['limit_reached']:
                raise ValueError('Body detector census is missing or truncated; repeat analysis before single-person review')
            field = BodySlimField(row, asset, shape)
            field.associated_face_id = face['face_instance_id']
            field.facts.update(associated_face_ref=deepcopy(asset['data']['associated_face_ref']),
                               associated_face_evidence_sha256=asset['data']['associated_face_evidence_sha256'])
            fields.append(field)
        except (ValueError, RuntimeError, OSError) as error:
            failures.append({'body_ref': deepcopy(ref), 'operation_id': S.OPERATION_ID,
                             'reason': str(error), 'requested_recipe': deepcopy(row['operations'][S.OPERATION_ID]['recipe']),
                             'applied': False})
    if failures:
        raise BodySlimRefused(failures)
    if sum(field.resident_bytes() for field in fields) > byte_budget:
        raise ValueError('Retained whole-body width fields exceed the admitted memory budget')
    return tuple(fields)
