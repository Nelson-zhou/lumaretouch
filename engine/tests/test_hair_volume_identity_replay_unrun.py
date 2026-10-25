# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Synthetic identity/replay contracts, not photo acceptance.

No product imports, tests, native execution, rendering or inference were run
while authoring these fixtures under the static-source-only authorization.
"""
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace
from unittest import mock
import numpy as np
import pytest
from lumaretouch_engine import people_algorithms as ALGORITHMS, people_resolver as RESOLVER
from lumaretouch_engine import people_state as P, people_geometry_identity as IDENTITY
from lumaretouch_engine import people_binding as BINDING, people_retained_analysis as RETAINED
from lumaretouch_engine import hair_volume_state as S, hair_volume_support as A
from lumaretouch_engine import hair_volume_project as PROJECT
from lumaretouch_engine import hair_colour_replay as REPLAY, hair_colour_evidence as SAVED
from test_hair_volume_contract_unrun import fixture


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def legacy_record(snapshot):
    """Pre-volume identity algorithm, retained here to compare exact bytes."""
    state = P.check(snapshot['state']); asset = P.digest(snapshot['asset_sha256']); faces = []
    for key, face in sorted(state['faces'].items()):
        if face['asset_sha256'] != asset or not face['enabled']:
            continue
        resolved = RESOLVER.resolve(state, key, ALGORITHMS.defaults())
        ops = (ALGORITHMS.DEFORM, *ALGORITHMS.GEOMETRY)
        values = {op: {path: item['value'] for path, item in resolved['operations'].get(op, {}).items()}
                  for op in ops}
        conflicts = [item for item in resolved['conflicts'] if item['operation_id'] in ops]
        if not conflicts and all(values[op] == ALGORITHMS.defaults()[op] for op in ops):
            continue
        faces.append({'face_ref': P.face_ref(face), 'evidence': face['evidence'],
                      'values': values, 'conflicts': conflicts})
    return {'asset_sha256': asset, 'faces': faces,
            'overlap_policy': 'stable_face_id_first_nonzero', 'composition': 'M(E(N(B(A(x)))))'}


@pytest.mark.parametrize('legacy_active', [False, True])
@pytest.mark.parametrize('unlinked', [False, True])
def test_no_active_volume_or_pointer_preserves_exact_legacy_bytes(legacy_active, unlinked):
    state, bank, source, _, record = fixture()
    state = A.detach(state, record['face_ref'])
    if legacy_active:
        path = sorted(ALGORITHMS.defaults()[ALGORITHMS.DEFORM])[0]
        state = P.set_override(state, 'face', 'owner', ALGORITHMS.DEFORM, path, .25)
    value = S.neutral(); value['sides']['linked'] = not unlinked
    state = PROJECT.set_recipe(state, 'owner', value)
    snapshot = {'state': state, 'asset_sha256': source['sha256'], 'support_assets': bank}
    expected = encoded(legacy_record(snapshot))
    assert encoded(IDENTITY.record(snapshot)) == expected
    assert IDENTITY.digest(snapshot) == sha256(expected).hexdigest()
    assert 'hair_volume' not in IDENTITY.record(snapshot)


def test_volume_identity_pins_scalars_owner_source_and_immutable_pointer():
    state, bank, source, _, record = fixture()
    snapshot = {'state': state, 'asset_sha256': source['sha256']}
    dormant = IDENTITY.digest(snapshot)
    value = S.neutral(); value['crown']['amount'] = .4
    state = PROJECT.set_recipe(state, 'owner', value); snapshot['state'] = state
    active = IDENTITY.digest(snapshot)
    assert active != dormant
    item = IDENTITY.record(snapshot)['hair_volume']['faces'][0]
    assert item == {'face_ref': record['face_ref'], 'source': source,
                    'evidence': state['faces']['owner']['evidence'], 'recipe': value,
                    'support': state['faces']['owner']['local_assets'][A.KIND]}
    assert item['support']['content_sha256'] == A.digest(record)
    assert IDENTITY.digest({**snapshot, 'support_assets': bank}) == active
    assert IDENTITY.digest({**snapshot, 'creative_source': source}) == active

    for mutate in (
        lambda face: face['local_assets'][A.KIND].__setitem__('content_sha256', 'f'*64),
        lambda face: face['evidence'].__setitem__('source_width', 1002),
        lambda face: face['evidence'].__setitem__('landmark_digest', 'f'*64),
    ):
        changed = deepcopy(state); mutate(changed['faces']['owner'])
        assert IDENTITY.digest({**snapshot, 'state': changed}) != active
    changed = deepcopy(state); changed['faces']['owner']['analysis_revision'] = 1
    changed['faces']['owner']['local_assets'][A.KIND]['owner']['analysis_revision'] = 1
    assert IDENTITY.digest({**snapshot, 'state': changed}) != active
    missing = A.detach(state, record['face_ref'])
    assert IDENTITY.digest({**snapshot, 'state': missing}) != active
    assert IDENTITY.record({**snapshot, 'state': missing})['hair_volume']['faces'][0]['support'] is None
    with pytest.raises(ValueError, match='effective source'):
        IDENTITY.record({**snapshot, 'creative_source': {**source, 'sha256': 'b'*64}})


def test_volume_identity_ignores_labels_cursor_archives_and_disabled_or_foreign_faces():
    state, bank, source, _, _ = fixture()
    snapshot = {'state': state, 'asset_sha256': source['sha256']}
    expected = IDENTITY.digest(snapshot)
    changed = deepcopy(state); changed['revision'] += 1
    changed['faces']['owner']['labels']['display'] = 'renamed'
    assert IDENTITY.digest({**snapshot, 'state': changed, 'selected_face': 'another',
                            'support_assets': {**bank, 'unused': 'not an identity input'}}) == expected
    changed['faces']['owner']['enabled'] = False
    assert IDENTITY.record({**snapshot, 'state': changed}) == legacy_record({**snapshot, 'state': changed})
    foreign = {**snapshot, 'asset_sha256': 'b'*64}
    assert IDENTITY.record(foreign) == legacy_record(foreign)


def replay_fixture():
    state, _, source, evidence, record = fixture()
    # These are explicitly synthetic fixture bytes, not a producer substitute.
    points = np.arange(478*3, dtype='<f4').reshape(478, 3) / np.float32(2000)
    face = state['faces']['owner']; face['evidence']['landmark_digest'] = BINDING.landmark_digest(points)
    record = A.reviewed(state, P.face_ref(face), source, record['row']['regions'],
                        record['row']['protection'], evidence, confirmed=True)
    state, bank = A.retain(state, {}, record)
    value = S.neutral(); value['crown']['amount'] = .4
    state = PROJECT.set_recipe(state, 'owner', value)
    row = {'face_ref': P.face_ref(face), 'evidence': face['evidence'], 'landmarks': points}
    engine = SimpleNamespace(_precompute=None, _people_support=bank,
        _people_landmarks=RETAINED.retain({}, {'owner': row}),
        _hair_colour_evidence={SAVED.identity(evidence): SAVED.encode(evidence)})
    return engine, state, source, evidence, record, points


def rebind_support(engine, state, record):
    record = deepcopy(record); del record['row']['review']
    record['row']['review'] = {'method': 'explicit_source_hair_geometry_review',
        'operation_id': S.OP, 'confirmed': True, 'review_key': A.digest(record)}
    state, engine._people_support = A.retain(state, {}, record)
    return state


def test_volume_only_replay_restores_exact_landmarks_without_inference_or_fake_semantics():
    engine, state, source, _, record, points = replay_fixture()
    with mock.patch.object(SAVED, 'current', side_effect=AssertionError('fresh analysis requested')):
        rows = REPLAY.analyses(engine, state, source)
    assert set(rows) == {'owner'} and engine._precompute is None
    row = rows['owner']
    assert row['face_ref'] == record['face_ref']
    assert row['evidence'] == state['faces']['owner']['evidence']
    assert row['landmarks'].tobytes() == points.tobytes()
    assert not row['landmarks'].flags.writeable
    assert row['excluded'] is None and row['skin'] is None
    assert 'face_skin' not in row and 'body_skin' not in row


def test_retained_neutral_volume_support_still_replays_without_rewriting_it():
    engine, state, source, _, _, _ = replay_fixture()
    state = PROJECT.set_recipe(state, 'owner', S.neutral())
    bank = deepcopy(engine._people_support)
    assert REPLAY.analyses(engine, state, source) is not None
    assert engine._people_support == bank


def test_replay_missing_or_changed_volume_support_is_not_repaired():
    engine, state, source, _, record, _ = replay_fixture()
    missing = A.detach(state, record['face_ref'])
    with pytest.raises(ValueError, match='per-region support'):
        REPLAY.analyses(engine, missing, source)
    engine._people_support = {}
    with pytest.raises(ValueError, match='missing'):
        REPLAY.analyses(engine, state, source)
    engine._people_support = {A.digest(record): deepcopy(record)}
    engine._people_support[A.digest(record)]['row']['regions']['crown']['x'][0] += .001
    with pytest.raises(ValueError):
        REPLAY.analyses(engine, state, source)


def test_replay_requires_the_same_semantic_bytes_and_real_probe_evidence():
    engine, state, source, evidence, record, _ = replay_fixture()
    changed = deepcopy(evidence); changed['weight'] = np.zeros_like(evidence['weight'])
    changed['weight_sha256'] = sha256(changed['weight'].tobytes()).hexdigest()
    engine._hair_colour_evidence = {SAVED.identity(changed): SAVED.encode(changed)}
    with pytest.raises(ValueError, match='different retained measured'):
        REPLAY.analyses(engine, state, source)
    # Even a re-keyed, structurally valid support cannot substitute a zero mask.
    record['row']['semantic_evidence_sha256'] = SAVED.identity(changed)
    state = rebind_support(engine, state, record)
    with pytest.raises(ValueError, match='hair interior lacks'):
        REPLAY.analyses(engine, state, source)


def test_replay_requires_each_active_region_and_unchanged_retained_source_census():
    engine, state, source, _, record, _ = replay_fixture()
    record['row']['regions']['crown'] = None
    state = rebind_support(engine, state, record)
    with pytest.raises(ValueError, match='own reviewed observed contour'):
        REPLAY.analyses(engine, state, source)
    engine, state, source, _, _, _ = replay_fixture()
    other = deepcopy(state['faces']['owner'])
    other.update(face_instance_id='retained-disabled', enabled=False, local_assets={})
    state['faces']['retained-disabled'] = other
    with pytest.raises(ValueError, match='ownership/boundaries changed'):
        REPLAY.analyses(engine, state, source)


def test_replay_refuses_foreign_source_shared_scope_and_unrelated_effects():
    engine, state, source, _, _, _ = replay_fixture()
    with pytest.raises(ValueError):
        REPLAY.analyses(engine, state, {**source, 'width': source['width'] + 1})
    assert REPLAY.analyses(engine, state, {**source, 'sha256': 'b'*64}) is None
    shared = P.set_override(state, 'all_people', source['sha256'], S.OP, '/crown/amount', .2)
    with pytest.raises(ValueError, match='no group'):
        REPLAY.analyses(engine, shared, source)
    path = sorted(ALGORITHMS.defaults()[ALGORITHMS.DEFORM])[0]
    non_hair = P.set_override(state, 'face', 'owner', ALGORITHMS.DEFORM, path, .25)
    assert REPLAY.analyses(engine, non_hair, source) is None


def test_replay_missing_landmarks_or_evidence_never_fabricates_them():
    engine, state, source, _, _, _ = replay_fixture()
    engine._hair_colour_evidence = {}
    assert REPLAY.analyses(engine, state, source) is None
    engine, state, source, _, _, _ = replay_fixture()
    engine._people_landmarks = {}
    assert REPLAY.analyses(engine, state, source) is None
    engine, state, source, _, record, _ = replay_fixture()
    engine._people_landmarks[RETAINED.key(record['face_ref'])]['landmarks'][0][0] += .01
    with pytest.raises(ValueError, match='corrupt'):
        REPLAY.analyses(engine, state, source)
