# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: lower-third length preset, canonical replay and transfer.

Targets LNX-REF-PC-32466-C-1ae8316994. Synthetic evidence and mocked native /
complete-render boundaries specify admission and routing, not real inference,
native numerical correctness, photographic quality or runtime acceptance.
No product import, test collection/execution, build or typecheck ran during
authoring. Legacy small-chin, corrected slim face, contour and whole-face size are not migrated.
Positive lengthens and negative shortens the local nose/chin proxy interval;
mouth participates, width and upper face are retained by this operation only,
and feathered neck/background can move. This is not clinical measurement, AI
or segmentation; these mocked boundary tests do not assert photographic quality.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest

from lumaretouch_engine import lower_face_scope as C, lower_face_state as S, lower_face_native as N
from lumaretouch_engine import face_contour_scope as CONTOUR, face_contour_native as CONTOUR_NATIVE
from lumaretouch_engine import slim_face_scope as SLIM
from lumaretouch_engine import face_size_scope as SIZE, face_size_native as SIZE_NATIVE
from lumaretouch_engine import people_state as P, people_algorithms as A, people_scope as REPLAY, scope as SC
from lumaretouch_engine import skin_colour_scope as COLOUR
from lumaretouch_engine.people_resolver import resolve
from lumaretouch_engine.workflow_ports import WorkflowPortsMixin
from test_skin_colour_scope_unrun import (ASSET, FACE, Owner, graph, endpoint,
    engine_fixture as colour_engine_fixture, isolate_other_captures)

LEAVES = ('/amount',)


def recipe(amount=0.):
    return {'recipe': {'version': 1, 'amount': amount}}


def engine_fixture(monkeypatch):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, analysis, current = colour_engine_fixture(monkeypatch)
    monkeypatch.setattr(N, 'available', lambda: True)
    engine._docs = [{'document_id': 'target-document', 'path': 'fixture.jpg', 'state': current}]
    engine._doc_index = 0
    versions = SimpleNamespace(workspace='workspace', version=lambda row:
        SimpleNamespace(document_id=row['document_id'], revision=2))
    engine._document_versions = lambda: versions
    monkeypatch.setattr(I.SOURCE, 'row_proof', lambda row: {'asset_sha256': ASSET,
        'creative_source': None, 'original_sha256': ASSET})
    return engine, owner, analysis, current


def replay_fixture(monkeypatch, *, fail=False):
    engine, owner, analysis, current = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch); calls = []
    def replay(state, **kwargs):
        calls.append((deepcopy(state), kwargs))
        if fail: raise RuntimeError('authored complete target-render refusal')
        return {'event': 'frame', 'render_ms': 0}
    engine._replay_state = replay
    return engine, owner, analysis, current, calls


def put(owner, amount):
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/amount', amount)


def values(owner):
    return A.recipes(resolve(owner.snapshot(), FACE, A.defaults()))


def test_separate_scalar_operation_preserves_legacy_and_generic_derived_admission():
    assert C.OP == 'lnx.lower_face.v1' and S.VERSION == 1
    assert S.CONTROL_ID == 'LNX-REF-PC-32466-C-1ae8316994'
    assert A.GEOMETRY == ('lnx.brow_shape.v1', 'lnx.nose_shape.v1', 'lnx.eye_shape.v1', 'lnx.mouth_shape.v1')
    assert C.OP not in A.GEOMETRY and C.OP not in SC.DERIVED_PARAMETER_OPS
    assert SC.MODULES[C.OP]['read'] is C.params_of
    assert SC.MODULES[C.OP]['write'] is C.install
    assert SC.MODULES[C.OP]['state_fields'] == (C.FIELD,)
    assert SC.MODULES[C.OP]['single_face'] is True
    assert A.defaults()[C.OP] == {'/amount': 0.}
    assert S.neutral() == recipe()['recipe'] and not S.active(S.neutral())
    assert A.defaults()[A.DEFORM]['/slim_face'] == 0.
    assert A.defaults()[A.DEFORM]['/small_chin'] == 0.
    assert A.defaults()[SIZE.OP] == {'/amount': 0.}
    assert A.defaults()[SLIM.OP] == {'/linked': True, '/left': 0., '/right': 0.}


@pytest.mark.parametrize('amount', [-1., -.4, 0., .3, 1.])
def test_only_one_signed_amount_round_trips_without_direction_conversion(amount):
    params = recipe(amount)
    assert C.check_params(params) == SC.check_params(C.OP, params) == params
    portable = {'schema': SC.PRESET_SCHEMA, 'id': 'lower-face', 'name': 'Lower-third length',
        'kind': 'portrait', 'modules': {C.OP: params}}
    loaded = SC.validate_preset(json.loads(SC.dump_preset(portable)))
    assert loaded['modules'] == {C.OP: params}
    assert set(loaded['modules'][C.OP]['recipe']) == {'version', 'amount'}
    assert set(A.leaves(loaded['modules'][C.OP]['recipe'])) == set(LEAVES)


@pytest.mark.parametrize('value', [True, False, None, '0.5', float('nan'), float('inf'),
    float('-inf'), -1.01, 1.01, 10**1000, -(10**1000)])
def test_invalid_scalar_refuses_without_mutating_transport_or_canonical_graph(monkeypatch, value):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    state = C.capture(engine); before = deepcopy(state)
    with pytest.raises(ValueError): C.install(state, recipe(value))
    assert state == before and not owner.commits


@pytest.mark.parametrize('key', ['linked', 'left', 'right', 'face_ref', 'owner', 'source', 'face_skin',
    'excluded', 'landmarks', 'analysis', 'mesh', 'control_points', 'displacement', 'mask',
    'coverage', 'supported', 'body_ref', 'ai', 'model_3d', 'small_chin', 'nose_y', 'chin_y', 'width', 'upper_face', 'mouth'])
def test_portable_shape_rejects_source_geometry_and_claimed_readiness(key):
    with pytest.raises(ValueError): C.check_params({**recipe(.3), key: {}})
    params = recipe(.3); params['recipe'][key] = {}
    with pytest.raises(ValueError): C.check_params(params)


@pytest.mark.parametrize('raw', [None, {}, {'version': 1}, {'amount': .3},
    {'version': True, 'amount': .3}, {'version': 2, 'amount': .3}, {'slim_face': .3}, {'small_chin': .3}])
def test_exact_versioned_scalar_is_not_an_alias_for_legacy_chin_or_slim_intent(raw):
    with pytest.raises(ValueError): C.check_params({'recipe': raw})


def test_workflow_capture_exports_canonical_amount_not_evidence_or_legacy_conversion(monkeypatch):
    engine, owner, analysis, current = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch); put(owner, .35)
    owner.value = P.set_override(owner.value, 'face', FACE, A.DEFORM, '/small_chin', -.6)
    owner.value = P.set_override(owner.value, 'face', FACE, SIZE.OP, '/amount', .2)
    current['_deform'] = {'amounts': {'small_chin': -.6}, 'built': True}
    before = owner.snapshot(); captured = WorkflowPortsMixin._people_preset_capture(engine)
    assert SC.params_of(captured, [C.OP]) == {C.OP: recipe(.35)}
    assert captured[C.TARGET] == P.face_ref(owner.value['faces'][FACE])
    assert captured['_lower_face_supported'] is True and captured[C.REQUESTED] is False
    assert C.owner_identity(captured) == {'document_id': 'target-document', 'epoch': 'workspace',
        'people_scope': 'project', 'source_proof': {'asset_sha256': ASSET,
            'creative_source': None, 'original_sha256': ASSET}}
    assert set(captured[C.OWNER]) == {'document', 'people_scope', 'state_revision',
        'association_revision', 'graph_sha256', 'source_proof'}
    assert 'face_skin' not in captured and 'landmarks' not in captured
    assert captured['_deform'] == current['_deform']
    assert engine._people_analyses[ASSET][FACE] is analysis
    assert owner.snapshot() == before and not owner.commits


@pytest.mark.parametrize('fault', ['face-skin', 'observation', 'excluded', 'ref', 'model',
    'landmark-bytes', 'landmark-count', 'synthetic', 'dimensions', 'donor-analysis', 'observation-source'])
def test_capture_needs_own_observed_skin_and_authenticated_478_landmarks(monkeypatch, fault):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    if fault == 'face-skin': analysis['face_skin'] = None
    elif fault == 'observation': analysis.pop('face_skin_observation')
    elif fault == 'excluded': analysis['excluded'] = None
    elif fault == 'ref': analysis['face_ref']['analysis_revision'] += 1
    elif fault == 'model': analysis['face_skin_observation']['semantic_model_sha256'] = 'f' * 64
    elif fault == 'observation-source': analysis['face_skin_observation']['source_sha256'] = 'e' * 64
    elif fault == 'landmark-bytes': analysis['landmarks'][0, 0] = .8
    elif fault == 'landmark-count':
        analysis['landmarks'] = analysis['landmarks'][:468]
        digest = sha256(analysis['landmarks'].tobytes()).hexdigest()
        owner.value['faces'][FACE]['evidence']['landmark_digest'] = digest
        analysis['evidence']['landmark_digest'] = digest
    elif fault == 'synthetic':
        owner.value['faces'][FACE]['evidence']['status'] = 'synthetic'
        analysis['evidence']['status'] = 'synthetic'
    elif fault == 'dimensions': engine._people_source = lambda: {'sha256': ASSET, 'width': 641, 'height': 480}
    else: engine._people_analyses[ASSET][FACE] = graph('e' * 64, 'donor-face')[1]
    captured = C.capture(engine)
    assert captured['_lower_face_supported'] is False
    with pytest.raises(ValueError): C.install(captured, recipe(.3))
    assert not owner.commits


@pytest.mark.parametrize('fault', ['no-cursor', 'group-target', 'stale-target', 'disabled', 'unmanaged', 'no-document'])
def test_selection_needs_exact_enabled_face_and_owner_not_cursor_alone(monkeypatch, fault):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    if fault == 'no-cursor': engine._people_cursors.clear()
    elif fault == 'group-target': engine._people_targets[ASSET] = {'scope': 'group', 'target_id': 'preserved'}
    elif fault == 'stale-target': engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    elif fault == 'disabled': owner.value['faces'][FACE]['enabled'] = False
    elif fault == 'unmanaged': engine._people_managed = lambda: False
    else: engine._docs.clear()
    captured = C.capture(engine)
    with pytest.raises(ValueError): C.params_of(captured)
    with pytest.raises(ValueError): C.install(captured, recipe())
    assert not owner.commits


def test_install_only_changes_dedicated_transport_and_keeps_generic_derived_refusal(monkeypatch):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    before = C.capture(engine); after = SC.apply_modules(before, {C.OP: recipe(.3)})
    assert {key for key in after if before.get(key) != after[key]} == {C.FIELD, C.REQUESTED}
    assert after[C.TARGET] == before[C.TARGET] and after[C.OWNER] == before[C.OWNER]
    with pytest.raises(ValueError, match='合成来源'): C.install({**before, '_creative_base': {}}, recipe())
    with pytest.raises(SC.ScopeError): SC.check_derived_modules({C.OP: recipe()})
    with pytest.raises(ValueError): SC.apply_modules({}, {C.OP: recipe(.3)})
    assert not owner.commits


def test_dedicated_native_capability_cannot_be_replaced_by_other_geometry_and_neutral_can_reset(monkeypatch):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    put(owner, .3)
    monkeypatch.setattr(CONTOUR_NATIVE, 'available', lambda: True)
    monkeypatch.setattr(SIZE_NATIVE, 'available', lambda: True)
    monkeypatch.setattr(N, 'available', lambda: False)
    with pytest.raises(ValueError, match='专用 Rust'): C.install(C.capture(engine), recipe(.4))
    engine._people_analyses.clear()
    state = C.capture(engine); C.install(state, recipe()); REPLAY.replay_preset(engine, state)
    assert values(owner)[C.OP] == S.neutral()
    assert calls[-1][1]['strict_local'] is True and not engine._people_analyses


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('observed', [False, True])
def test_capture_reports_observed_support_separately_from_native_abi(monkeypatch, native, observed):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    monkeypatch.setattr(N, 'available', lambda: native)
    if not observed: analysis.pop('face_skin_observation')
    captured = C.capture(engine)
    assert captured['_lower_face_supported'] is observed
    assert captured['_lower_face_native_available'] is native
    # A valid exact owner/FaceRef still permits neutral recovery independently.
    C.install(captured, recipe())
    assert C.params_of(captured) == recipe() and not owner.commits
    if native and observed:
        C.install(captured, recipe(-.4))
        assert C.params_of(captured) == recipe(-.4)
    else:
        with pytest.raises(ValueError): C.install(captured, recipe(-.4))


@pytest.mark.parametrize('amount', [-.6, .6])
def test_legacy_small_chin_is_retained_and_never_inferred_as_lower_third_length(monkeypatch, amount):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, A.DEFORM, '/small_chin', amount)
    before = owner.snapshot(); state = C.capture(engine)
    assert C.params_of(state) == recipe()
    C.install(state, recipe()); REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and len(calls) == 1
    assert values(owner)[A.DEFORM]['small_chin'] == amount


@pytest.mark.parametrize('amount', [0., .3])
def test_source_proof_mismatch_refuses_even_neutral_and_cannot_claim_target_ownership(monkeypatch, amount):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, _, _ = engine_fixture(monkeypatch)
    monkeypatch.setattr(I.SOURCE, 'row_proof', lambda row: {'asset_sha256': 'e' * 64,
        'creative_source': None, 'original_sha256': 'e' * 64})
    state = C.capture(engine); before = deepcopy(state)
    assert state['_lower_face_supported'] is False
    with pytest.raises(ValueError, match='有效来源'): C.install(state, recipe(amount))
    assert state == before and not owner.commits


@pytest.mark.parametrize('fault', ['native', 'analysis', 'target', 'unmanaged', 'source',
    'document', 'owner', 'epoch', 'proof', 'source-kind', 'original-source'])
def test_replay_rechecks_live_owner_and_readiness_not_captured_flags(monkeypatch, fault):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(.3))
    if fault == 'native': monkeypatch.setattr(N, 'available', lambda: False)
    elif fault == 'analysis': analysis['excluded'] = None
    elif fault == 'target': engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    elif fault == 'unmanaged': engine._people_managed = lambda: False
    elif fault == 'source': engine._people_source = lambda: {'sha256': 'e' * 64, 'width': 640, 'height': 480}
    elif fault == 'document': engine._docs[0]['document_id'] = 'another-document'
    elif fault == 'owner': engine._docs[0]['copy_number'] = 1
    elif fault == 'epoch': engine._document_versions().workspace = 'another-workspace'
    elif fault == 'proof': state.pop(C.OWNER)
    elif fault == 'source-kind':
        state[C.OWNER]['source_proof']['creative_source'] = {'sha256': ASSET, 'width': 640, 'height': 480}
    else: state[C.OWNER]['source_proof']['original_sha256'] = 'f' * 64
    before = owner.snapshot()
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


@pytest.mark.parametrize('fault', ['document', 'epoch', 'owner', 'target'])
def test_neutral_reset_never_bypasses_changed_owner_or_face(monkeypatch, fault):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    put(owner, .3); state = C.capture(engine); C.install(state, recipe())
    engine._people_analyses.clear(); monkeypatch.setattr(N, 'available', lambda: False)
    if fault == 'document': engine._docs[0]['document_id'] = 'other-document'
    elif fault == 'epoch': engine._document_versions().workspace = 'other-workspace'
    elif fault == 'owner': engine._docs[0]['copy_number'] = 1
    else: engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    before = owner.snapshot()
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


def test_same_source_face_switch_refuses_capture_even_when_only_one_remains_enabled(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(.3))
    other, analysis = graph(face_id='another-face')
    owner.value['faces']['another-face'] = other['faces']['another-face']
    owner.value['faces'][FACE]['enabled'] = False
    engine._people_analyses[ASSET]['another-face'] = analysis
    engine._people_cursors[ASSET] = 'another-face'
    engine._people_targets[ASSET] = {'scope': 'face', 'target_id': 'another-face',
        'face_ref': P.face_ref(other['faces']['another-face'])}
    before = owner.snapshot()
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


@pytest.mark.parametrize('retained_op,path,value', [(A.DEFORM, '/small_chin', -.6),
    (A.DEFORM, '/slim_face', -.4), (SLIM.OP, '/left', .4),
    (CONTOUR.OP, '/jaw/right', -.2), (SIZE.OP, '/amount', .25)])
@pytest.mark.parametrize('refused', [False, True])
def test_complete_candidate_preserves_other_geometry_and_renderer_owns_composition(monkeypatch, retained_op, path, value, refused):
    engine, owner, analysis, _, _ = replay_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'group', 'preserved', retained_op, path, value)
    owner.value = P.set_override(owner.value, 'face', FACE, COLOUR.OP, '/tint', -.25)
    before = owner.snapshot(); rendered = []
    def render(state, **kwargs):
        candidate = owner.snapshot(); rendered.append(candidate)
        assert kwargs['strict_local'] is True
        assert values(owner)[C.OP] == recipe(.35)['recipe']
        assert all(row in candidate['overrides'] for row in before['overrides'])
        for field in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
            assert candidate[field] == before[field]
        assert [row for row in candidate['overrides'] if row not in before['overrides']] == [
            {'scope': 'face', 'target_id': FACE, 'operation_id': C.OP, 'parameter_path': '/amount', 'value': .35}]
        if refused: raise RuntimeError('complete candidate composition refused')
        return {'event': 'frame'}
    engine._replay_state = render
    state = C.capture(engine); C.install(state, recipe(.35))
    if refused:
        with pytest.raises(RuntimeError, match='composition refused'): REPLAY.replay_preset(engine, state)
        assert owner.snapshot() == before and len(owner.commits) == 2
    else:
        REPLAY.replay_preset(engine, state)
        assert len(owner.commits) == 1
    assert len(rendered) == 1 and engine._people_analyses[ASSET][FACE] is analysis


@pytest.mark.parametrize('refused', [False, True])
def test_simultaneous_size_and_lower_third_candidate_is_one_transaction_without_legacy_conversion(monkeypatch, refused):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch)
    monkeypatch.setattr(SIZE_NATIVE, 'available', lambda: True)
    owner.value = P.set_override(owner.value, 'face', FACE, A.DEFORM, '/small_chin', -.45)
    before = owner.snapshot(); rendered = []
    state = WorkflowPortsMixin._people_preset_capture(engine)
    after = SC.apply_modules(state, {SIZE.OP: recipe(-.2), C.OP: recipe(.4)})
    def render(actual, **kwargs):
        candidate = owner.snapshot(); rendered.append(candidate)
        assert kwargs['strict_local'] is True
        assert values(owner)[C.OP] == recipe(.4)['recipe']
        assert values(owner)[SIZE.OP] == recipe(-.2)['recipe']
        assert values(owner)[A.DEFORM]['small_chin'] == -.45
        assert all(leaf in candidate['overrides'] for leaf in before['overrides'])
        added = [leaf for leaf in candidate['overrides'] if leaf not in before['overrides']]
        assert {(leaf['operation_id'], leaf['parameter_path'], leaf['value']) for leaf in added} == {
            (SIZE.OP, '/amount', -.2), (C.OP, '/amount', .4)}
        if refused: raise RuntimeError('complete combined geometry refused')
        return {'event': 'frame'}
    engine._replay_state = render
    if refused:
        with pytest.raises(RuntimeError, match='complete combined geometry refused'):
            REPLAY.replay_preset(engine, after)
        assert owner.snapshot() == before and len(owner.commits) == 2
    else:
        REPLAY.replay_preset(engine, after)
        assert len(owner.commits) == 1
    assert len(rendered) == 1 and engine._people_analyses[ASSET][FACE] is analysis


def test_unchanged_active_lower_third_still_uses_strict_complete_target_renderer(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    put(owner, -.3); REPLAY.replay_preset(engine, C.capture(engine))
    assert not owner.commits and calls[-1][1]['strict_local'] is True


def test_neutral_lower_third_reset_does_not_erase_other_retained_geometry(monkeypatch):
    # Mock render isolates reset ownership: retained effects can independently
    # refuse in the actual renderer and are never claimed runnable by this test.
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    put(owner, -.3)
    for op, path, value in ((A.DEFORM, '/small_chin', -.6), (A.DEFORM, '/slim_face', -.4),
            (SLIM.OP, '/left', .2), (CONTOUR.OP, '/jaw/right', .3), (SIZE.OP, '/amount', -.25)):
        owner.value = P.set_override(owner.value, 'face', FACE, op, path, value)
    retained = [deepcopy(row) for row in owner.value['overrides'] if row['operation_id'] != C.OP]
    engine._people_analyses.clear(); monkeypatch.setattr(N, 'available', lambda: False)
    state = C.capture(engine); C.install(state, recipe()); REPLAY.replay_preset(engine, state)
    assert values(owner)[C.OP] == S.neutral()
    assert [row for row in owner.value['overrides'] if row['operation_id'] != C.OP] == retained
    assert calls[-1][1]['strict_local'] is True


def test_failed_render_restores_graph_and_existing_outer_history_rollback_replays(monkeypatch):
    from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
    from lumaretouch_engine.preset_transaction import apply_with_rollback, PresetApplyError
    engine, initial, _, _, _ = replay_fixture(monkeypatch)
    owner = PeopleGraphOwner(initial.snapshot()); engine._people_owner = lambda: owner
    before_graph = owner.snapshot(); before = C.capture(engine); after = deepcopy(before)
    C.install(after, recipe(.3)); calls = []
    def render(state, **kwargs):
        calls.append((deepcopy(state), kwargs))
        if len(calls) == 1: raise RuntimeError('authored complete target-render refusal')
        return {'event': 'frame'}
    engine._replay_state = render
    with pytest.raises(PresetApplyError) as error:
        apply_with_rollback(lambda state, **kwargs: REPLAY.replay_preset(engine, state, **kwargs),
            before, after, preset_id='lower-face', emit=lambda event: None,
            invalidate=lambda: pytest.fail('Rollback must remain available'))
    assert error.value.rolled_back is True and len(calls) == 2
    assert calls[0][1]['strict_local'] is True and calls[1][1]['mode'] == 'preset_rollback'
    actual = owner.snapshot()
    assert actual['revision'] == before_graph['revision'] + 2 and owner.fence == 2
    assert {key: value for key, value in actual.items() if key != 'revision'} == {
        key: value for key, value in before_graph.items() if key != 'revision'}


def test_generic_preset_never_guesses_between_enabled_faces(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    other, _ = graph(face_id='neighbour-face'); owner.value['faces']['neighbour-face'] = other['faces']['neighbour-face']
    before = owner.snapshot(); state = C.capture(engine); C.install(state, recipe(.3))
    with pytest.raises(ValueError, match='one explicit unambiguous enabled face'): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


def test_unrelated_replay_needs_no_lower_third_target_document_or_analysis(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    engine._people_targets.clear(); engine._docs.clear(); engine._people_analyses.clear()
    REPLAY.replay_preset(engine, {})
    assert not owner.commits and len(calls) == 1 and C.FIELD not in calls[0][0]


def test_capture_authenticates_live_baseline_not_parked_document_state(monkeypatch):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, _, current = engine_fixture(monkeypatch)
    current['audit_marker'] = 'live'; engine._docs[0]['state'] = {'audit_marker': 'parked'}
    observed = []
    def source_proof(row):
        observed.append(deepcopy(row['state'])); assert row['state']['audit_marker'] == 'live'
        return {'asset_sha256': ASSET, 'creative_source': None, 'original_sha256': ASSET}
    monkeypatch.setattr(I.SOURCE, 'row_proof', source_proof)
    assert C.params_of(C.capture(engine)) == recipe() and observed == [current]
    assert engine._docs[0]['state'] == {'audit_marker': 'parked'} and not owner.commits


@pytest.mark.parametrize('reused_original_analysis', [False, True])
def test_derived_capture_uses_effective_source_and_never_original_analysis(monkeypatch, reused_original_analysis):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, original_analysis, current = engine_fixture(monkeypatch)
    derived = 'e' * 64; target, own_analysis = graph(derived)
    owner.value = target; ref = P.face_ref(target['faces'][FACE])
    engine._people_source = lambda: {'sha256': derived, 'width': 640, 'height': 480}
    engine._people_cursors = {derived: FACE}
    engine._people_targets = {derived: {'scope': 'face', 'target_id': FACE, 'face_ref': ref}}
    engine._people_analyses = {ASSET: {FACE: original_analysis}, derived: {FACE:
        original_analysis if reused_original_analysis else own_analysis}}
    current['_creative_base'] = {'fixture': 'derived baseline, not product pixels'}
    monkeypatch.setattr(I.SOURCE, 'row_proof', lambda row: {'asset_sha256': derived,
        'creative_source': {'sha256': derived, 'width': 640, 'height': 480}, 'original_sha256': ASSET})
    put(owner, .3); captured = C.capture(engine)
    assert captured['_lower_face_supported'] is (not reused_original_analysis)
    if reused_original_analysis:
        with pytest.raises(ValueError): C.params_of(captured)
    else:
        assert C.params_of(captured) == recipe(.3)
        assert C.owner_identity(captured)['source_proof']['asset_sha256'] == derived
    # Even authentic effective-source analysis does not expand the generic route.
    with pytest.raises(ValueError, match='合成来源'): C.install(captured, recipe())
    assert not owner.commits


def test_confirmed_batch_selects_amount_only_not_version_identity_or_geometry():
    from lumaretouch_engine import people_batch_transfer as B
    value, _ = graph(); selected = {'source_ref': P.face_ref(value['faces'][FACE]),
        'selection': {C.OP: list(LEAVES)}, 'target_policy': 'confirmed_person_only'}
    assert B.options(selected, [C.OP], ASSET) == selected
    for path in ('/version', '/linked', '/left', '/slim_face', '/small_chin', '/face_ref', '/face_skin', '/landmarks', '/mask', '/control_points', '/supported'):
        wrong = deepcopy(selected); wrong['selection'][C.OP] = [path]
        with pytest.raises(ValueError, match='scalar parameter leaves'): B.options(wrong, [C.OP], ASSET)


@pytest.mark.parametrize('target_policy', ['explicit_face_map', 'confirmed_person_only'])
def test_selected_amount_transfer_preserves_target_assets_other_geometry_and_owner_fences(target_policy):
    from lumaretouch_engine import people_transfer_adapter as T
    from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed
    source, _ = graph(face_id='source-face'); target, _ = graph('e' * 64)
    for value, face_id in ((source, 'source-face'), (target, FACE)):
        value['persons']['confirmed-person'] = {'anonymous': True}
        value['links'] = [{'face_instance_id': face_id, 'person_id': 'confirmed-person',
            'state': 'confirmed', 'confirmation_revision': 0}]
    source = P.set_override(source, 'face', 'source-face', C.OP, '/amount', -.4)
    target = P.set_override(target, 'face', FACE, C.OP, '/amount', .2)
    target = P.set_override(target, 'group', 'preserved', SLIM.OP, '/right', .3)
    target = P.set_override(target, 'face', FACE, A.DEFORM, '/small_chin', -.5)
    target = P.set_override(target, 'face', FACE, SIZE.OP, '/amount', .2)
    scope = 'project' if target_policy == 'confirmed_person_only' else None
    source_owner = endpoint(source, 'source', scope=scope); target_owner = endpoint(target, 'target', scope=scope)
    kwargs = {'source_document': source_owner['document'], 'target_document': target_owner['document'],
        'source_owner': source_owner, 'target_owner': target_owner}
    selection = {C.OP: list(LEAVES)}
    if target_policy == 'confirmed_person_only':
        payload = prepare_confirmed(source, target, P.face_ref(source['faces']['source-face']), 'e' * 64,
            selection, A.defaults(), **kwargs)
    else:
        payload = T.prepare(source, target, P.face_ref(source['faces']['source-face']),
            [P.face_ref(target['faces'][FACE])], selection, A.defaults(), **kwargs)
        payload['target_policy'] = target_policy
    candidate = T.candidate(payload, source, target, **kwargs)
    assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': '/amount', 'value': -.4}]
    assert {leaf['parameter_path']: leaf['value'] for leaf in candidate['overrides']
        if leaf['operation_id'] == C.OP} == {'/amount': -.4}
    assert all(leaf in candidate['overrides'] for leaf in target['overrides'] if leaf['operation_id'] != C.OP)
    assert candidate['faces'] == target['faces'] and candidate['links'] == target['links']
    assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
    changed = deepcopy(target_owner); changed['source_proof'] = {'asset_sha256': 'f' * 64,
        'creative_source': None, 'original_sha256': 'f' * 64}
    with pytest.raises(ValueError, match='owner, source or graph changed'):
        T.verify(payload, source, target, **{**kwargs, 'target_owner': changed})


@pytest.mark.parametrize('target_policy', ['explicit_face_map', 'confirmed_person_only'])
@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('refused_target', [None, 'target-b'])
def test_each_original_or_derived_target_recalculates_own_full_source_not_donor_geometry(monkeypatch, target_policy, derived, refused_target):
    """Actual preflight routing, mocked pixels only; no render-quality claim."""
    from lumaretouch_engine import people_batch_transfer as B, people_transfer_inventory as I
    from lumaretouch_engine import full_candidate_render as FULL
    source, _ = graph(face_id='source-face')
    target_a, _ = graph('e' * 64, 'target-a-face'); target_b, _ = graph('f' * 64, 'target-b-face')
    states = {'source': source, 'target-a': target_a, 'target-b': target_b}
    face_ids = {'source': 'source-face', 'target-a': 'target-a-face', 'target-b': 'target-b-face'}
    if target_policy == 'confirmed_person_only':
        for identity, value in states.items():
            value['persons']['confirmed-person'] = {'anonymous': True}
            value['links'] = [{'face_instance_id': face_ids[identity], 'person_id': 'confirmed-person',
                'state': 'confirmed', 'confirmation_revision': 0}]
    params = recipe(.3)
    for path, value in A.leaves(params['recipe']).items():
        source = P.set_override(source, 'face', 'source-face', C.OP, path, value)
    states['source'] = source
    for identity in ('target-a', 'target-b'):
        states[identity] = P.set_override(states[identity], 'face', face_ids[identity], COLOUR.OP, '/tint', -.2)
        states[identity] = P.set_override(states[identity], 'face', face_ids[identity], A.DEFORM, '/small_chin', -.45)
        states[identity] = P.set_override(states[identity], 'face', face_ids[identity], SIZE.OP, '/amount', .2)
        states[identity]['faces'][face_ids[identity]]['local_assets']['target-only']['content_sha256'] = (
            '1' if identity == 'target-a' else '2') * 64
    owner = Owner(source)
    rows = [{'document_id': identity, 'path': identity + '.jpg', 'state': {}} for identity in states]
    if derived:
        for row in rows[1:]: row['state']['_creative_base'] = {'fixture': row['document_id'] + ' immutable source'}
    def proof(value, identity):
        out = endpoint(value, identity, scope='project' if target_policy == 'confirmed_person_only' else None)
        if derived and identity != 'source':
            asset = value['faces'][face_ids[identity]]['asset_sha256']
            out['source_proof']['creative_source'] = {'sha256': asset, 'width': 640, 'height': 480}
            out['source_proof']['original_sha256'] = '3' * 64
        return out
    versions = SimpleNamespace(workspace='workspace', version=lambda row:
        SimpleNamespace(document_id=row['document_id'], revision=2))
    batch = SimpleNamespace(versions=versions,
        documents=SimpleNamespace(rows=lambda: rows, current_index=lambda: 0, remember_current=lambda: None),
        target_indices=lambda docs: ([1, 2], []))
    engine = SimpleNamespace(_people_bind=lambda: None, _people_owner=lambda: owner,
        _batch_controller=lambda: batch, _document_versions=lambda: versions,
        _body_bank=lambda: pytest.fail('Lower-third length does not acquire body coverage'))
    monkeypatch.setattr(B.V, 'row_snapshot', lambda actual_engine, row: deepcopy(states[row['document_id']]))
    monkeypatch.setattr(I, 'proof', lambda actual_engine, row, value: proof(value, row['document_id']))
    def verify(actual_engine, row, value, expected):
        assert expected == proof(value, row['document_id']); return expected
    monkeypatch.setattr(I, 'verify', verify)
    monkeypatch.setattr(B.SOURCE, 'row_proof', lambda row: proof(states[row['document_id']], row['document_id'])['source_proof'])
    def verify_source(row, expected):
        assert expected == B.SOURCE.row_proof(row); return expected
    monkeypatch.setattr(B.SOURCE, 'verify_row', verify_source)
    renders = []
    expected_parameters = [{'operation_id': C.OP, 'parameter_path': path, 'value': value}
        for path, value in sorted(A.leaves(params['recipe']).items())]
    def render(actual_engine, row, state, document_id, revision, *, people_graph):
        assert actual_engine is engine and row['document_id'] == document_id
        assert state is row['state'] and revision == '2' and document_id != 'source'
        target = states[document_id]; face_id = face_ids[document_id]
        for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
            assert people_graph[key] == target[key]
        added = [leaf for leaf in people_graph['overrides'] if leaf not in target['overrides']]
        assert sorted(added, key=lambda leaf: leaf['parameter_path']) == [
            {'scope': 'face', 'target_id': face_id, **leaf} for leaf in expected_parameters]
        assert all(leaf in people_graph['overrides'] for leaf in target['overrides'])
        renders.append((document_id, deepcopy(people_graph)))
        if document_id == refused_target:
            raise ValueError('Target-owned lower-face renderer refused spatial or photometric support')
        return None, {'fixture': 'routing only'}
    monkeypatch.setattr(FULL, 'render', render)
    plans = []
    def freeze(workspace, source_id, revision, path, modules, params, policy, targets, rejected):
        plans.append(targets)
        return SimpleNamespace(modules=modules, token='fixture-token', workspace=workspace, expires_ns=1)
    replies = []; controller = SimpleNamespace(store=SimpleNamespace(create=freeze), _source=lambda plan: {},
        emit=lambda event: None, emit_result=lambda request, body: replies.append(body))
    request = {'cmd': 'batch', 'action': 'preflight', 'request_id': 'fixture-lower-face',
        'docs': ['target-a', 'target-b'], 'module_scope': [C.OP], 'people_transfer': {
            'source_ref': P.face_ref(source['faces']['source-face']), 'selection': {C.OP: list(LEAVES)},
            'target_policy': 'explicit_face_map', 'source': proof(source, 'source'), 'targets': [
                {'target': proof(states[identity], identity),
                 'target_refs': [P.face_ref(states[identity]['faces'][face_ids[identity]])]}
                for identity in ('target-a', 'target-b')]}}
    if target_policy == 'confirmed_person_only':
        request['people_transfer'] = {key: value for key, value in request['people_transfer'].items()
            if key not in ('source', 'targets')}
        request['people_transfer']['target_policy'] = target_policy
    before = deepcopy(states); B.preflight(engine, controller, request)
    assert states == before and not owner.commits
    assert [identity for identity, _ in renders] == ['target-a', 'target-b']
    result = replies[-1]
    assert (result['ok'], result['blocked']) == ((1, 1) if refused_target else (2, 0))
    for index, identity in enumerate(('target-a', 'target-b')):
        payload = result['targets'][index]['people_transfer']
        if identity == refused_target:
            assert payload is None and plans[0][index].people_json is None
            assert 'Target-owned lower-face renderer refused' in result['targets'][index]['blocked']
        else:
            assert payload['parameters'] == expected_parameters
            assert payload['target_refs'] == [P.face_ref(states[identity]['faces'][face_ids[identity]])]
            assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
            assert not any('coverage' in key or 'support' in key for key in payload)
            assert json.loads(plans[0][index].people_json) == payload
