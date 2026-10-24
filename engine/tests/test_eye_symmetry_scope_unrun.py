# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: portable symmetry policy, identity and full-target routing.

These synthetic schema fixtures and mocked render boundaries are not inference,
native execution, photographic acceptance or proof of visible eye geometry.
No product imports, collection, tests, build or typecheck ran during authoring.
Auto is a policy to remeasure EACH target, never a donor's selected eye or size.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest

from lumaretouch_engine import eye_symmetry_scope as C, eye_symmetry_state as S, eye_symmetry_native as N
from lumaretouch_engine import people_state as P, people_algorithms as A, people_scope as REPLAY, scope as SC
from lumaretouch_engine import chin_length_scope as LENGTH, philtrum_scope as PHILTRUM
from lumaretouch_engine.people_resolver import resolve
from lumaretouch_engine.workflow_ports import WorkflowPortsMixin
from test_skin_colour_scope_unrun import (ASSET, FACE, Owner, graph, endpoint,
    engine_fixture as colour_engine_fixture, isolate_other_captures)

LEAVES = ('/horizontal', '/reference', '/size')


def recipe(horizontal=0., size=0., reference='auto'):
    return {'recipe': {'version': 1, 'horizontal': horizontal, 'size': size, 'reference': reference}}


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


def replay_fixture(monkeypatch):
    engine, owner, analysis, current = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch); calls = []
    def render(state, **kwargs):
        calls.append((deepcopy(state), kwargs)); return {'event': 'frame'}
    engine._replay_state = render
    return engine, owner, analysis, current, calls


def put(owner, horizontal=0., size=0., reference='auto'):
    for path, value in A.leaves(recipe(horizontal, size, reference)['recipe']).items():
        owner.value = P.set_override(owner.value, 'face', FACE, C.OP, path, value)


def values(owner):
    return A.recipes(resolve(owner.snapshot(), FACE, A.defaults()))


def test_exact_registration_keeps_reference_policy_out_of_geometry_and_generic_derived():
    assert C.OP == 'lnx.eye_symmetry.v1' and S.VERSION == 1
    assert A.defaults()[C.OP] == {'/horizontal': 0., '/size': 0., '/reference': 'auto'}
    assert C.OP not in A.GEOMETRY and C.OP not in SC.DERIVED_PARAMETER_OPS
    assert C.OP != 'lnx.eye_shape.v1' and C.OP != A.DEFORM
    assert SC.MODULES[C.OP]['read'] is C.params_of
    assert SC.MODULES[C.OP]['write'] is C.install
    assert SC.MODULES[C.OP]['state_fields'] == (C.FIELD,)
    assert SC.MODULES[C.OP]['single_face'] is True
    assert S.neutral() == recipe()['recipe']


@pytest.mark.parametrize('reference', ['auto', 'left', 'right'])
@pytest.mark.parametrize('horizontal,size', [(0., 0.), (.3, 0.), (0., .4), (1., 1.)])
def test_exact_strengths_and_reference_policy_round_trip(reference, horizontal, size):
    params = recipe(horizontal, size, reference)
    assert C.check_params(params) == SC.check_params(C.OP, params) == params
    preset = {'schema': SC.PRESET_SCHEMA, 'id': 'eye-symmetry', 'name': 'Eye symmetry',
        'kind': 'portrait', 'modules': {C.OP: params}}
    loaded = SC.validate_preset(json.loads(SC.dump_preset(preset)))
    assert loaded['modules'] == {C.OP: params}
    assert set(loaded['modules'][C.OP]['recipe']) == {'version', 'horizontal', 'size', 'reference'}
    assert set(A.leaves(params['recipe'])) == set(LEAVES)
    assert S.active(params['recipe']) is (horizontal != 0. or size != 0.)


@pytest.mark.parametrize('key', ['horizontal', 'size'])
@pytest.mark.parametrize('value', [True, False, None, '0.5', float('nan'), float('inf'),
    float('-inf'), -.01, 1.01, 10**1000, -(10**1000)])
def test_invalid_strength_refuses_without_mutation(monkeypatch, key, value):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    state = C.capture(engine); before = deepcopy(state); params = recipe()
    params['recipe'][key] = value
    with pytest.raises(ValueError): C.install(state, params)
    assert state == before and not owner.commits


@pytest.mark.parametrize('value', ['', 'LEFT', 'Right', 'larger', 'source-left', 'auto ',
    '/reference', 0, 1, True, None, {}, ['left']])
def test_reference_is_closed_enum_not_arbitrary_string_or_source_eye(value):
    with pytest.raises(ValueError): C.check_params(recipe(.3, .4, value))


@pytest.mark.parametrize('raw', [None, {}, {'version': 1},
    {'horizontal': .3, 'size': .4, 'reference': 'auto'},
    {'version': True, 'horizontal': .3, 'size': .4, 'reference': 'auto'},
    {'version': 2, 'horizontal': .3, 'size': .4, 'reference': 'auto'}])
def test_complete_exact_versioned_recipe_required(raw):
    with pytest.raises(ValueError): C.check_params({'recipe': raw})


@pytest.mark.parametrize('key', ['face_ref', 'owner', 'source', 'pixels', 'left_eye', 'right_eye',
    'landmarks', 'analysis', 'mask', 'excluded', 'control_points', 'displacement',
    'supported', 'native_available', 'reference_eye', 'actual_reference', 'selected_side',
    'measured_size', 'measured_level', 'level_delta', 'size_ratio', 'donor', 'source_ref',
    'clinical', 'semantic_segmentation', 'model_3d', 'linked', 'left', 'right', 'big_eye'])
def test_no_source_eye_pixels_measurements_actual_reference_or_readiness_can_travel(key):
    with pytest.raises(ValueError): C.check_params({**recipe(.3, .4), key: {}})
    params = recipe(.3, .4); params['recipe'][key] = {}
    with pytest.raises(ValueError): C.check_params(params)


def test_workflow_capture_reads_live_owner_and_only_portable_policy(monkeypatch):
    engine, owner, analysis, current = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch); put(owner, .3, .4, 'right')
    owner.value = P.set_override(owner.value, 'face', FACE, A.DEFORM, '/big_eye', .2)
    before = owner.snapshot(); captured = WorkflowPortsMixin._people_preset_capture(engine)
    assert SC.params_of(captured, [C.OP]) == {C.OP: recipe(.3, .4, 'right')}
    assert captured[C.TARGET] == P.face_ref(owner.value['faces'][FACE])
    assert captured['_eye_symmetry_supported'] is True and captured[C.REQUESTED] is False
    assert C.owner_identity(captured) == {'document_id': 'target-document', 'epoch': 'workspace',
        'people_scope': 'project', 'source_proof': {'asset_sha256': ASSET,
            'creative_source': None, 'original_sha256': ASSET}}
    assert set(captured[C.OWNER]) == {'document', 'people_scope', 'state_revision',
        'association_revision', 'graph_sha256', 'source_proof'}
    assert not {'landmarks', 'excluded', 'reference_eye', 'measured_size', 'pixels'} & set(captured)
    assert engine._people_analyses[ASSET][FACE] is analysis
    assert owner.snapshot() == before and not owner.commits and current == {}


@pytest.mark.parametrize('fault', ['excluded', 'ref', 'model', 'landmark-bytes',
    'landmark-count', 'synthetic', 'dimensions', 'donor'])
def test_active_capture_needs_authenticated_own_478_and_occluder_analysis(monkeypatch, fault):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    if fault == 'excluded': analysis['excluded'] = None
    elif fault == 'ref': analysis['face_ref']['analysis_revision'] += 1
    elif fault == 'model': analysis['evidence']['semantic_model_sha256'] = 'f' * 64
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
    assert captured['_eye_symmetry_supported'] is False
    with pytest.raises(ValueError): C.install(captured, recipe(.3, .4))
    assert not owner.commits


@pytest.mark.parametrize('fault', ['no-cursor', 'group-target', 'stale-target', 'disabled', 'unmanaged', 'no-document'])
def test_even_dormant_policy_needs_exact_enabled_face_and_owner(monkeypatch, fault):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    if fault == 'no-cursor': engine._people_cursors.clear()
    elif fault == 'group-target': engine._people_targets[ASSET] = {'scope': 'group', 'target_id': 'preserved'}
    elif fault == 'stale-target': engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    elif fault == 'disabled': owner.value['faces'][FACE]['enabled'] = False
    elif fault == 'unmanaged': engine._people_managed = lambda: False
    else: engine._docs.clear()
    captured = C.capture(engine)
    with pytest.raises(ValueError): C.params_of(captured)
    with pytest.raises(ValueError): C.install(captured, recipe(reference='right'))
    assert not owner.commits


@pytest.mark.parametrize('reference', ['auto', 'left', 'right'])
def test_zero_strength_recovery_needs_no_anatomy_or_native_with_retained_reference(monkeypatch, reference):
    engine, owner, _, _, calls = replay_fixture(monkeypatch); put(owner, .3, .4)
    owner.value = P.set_override(owner.value, 'face', FACE, A.DEFORM, '/big_eye', .2)
    before = deepcopy(owner.value['overrides']); engine._people_analyses.clear()
    monkeypatch.setattr(N, 'available', lambda: False)
    captured = C.capture(engine); C.install(captured, recipe(reference=reference))
    assert C.params_of(captured) == recipe(reference=reference)
    REPLAY.replay_preset(engine, captured)
    assert values(owner)[C.OP] == recipe(reference=reference)['recipe']
    assert all(row in owner.value['overrides'] for row in before if row['operation_id'] != C.OP)
    assert calls[-1][1]['strict_local'] is True


def test_capture_support_never_claims_both_eyes_pass_complete_render(monkeypatch):
    engine, owner, _, _, _ = replay_fixture(monkeypatch)
    state = C.capture(engine); assert state['_eye_symmetry_supported'] is True
    C.install(state, recipe(.3, .4, 'left')); before = owner.snapshot()
    def refuse(state, **kwargs):
        assert kwargs['strict_local'] is True
        raise ValueError('target right eye RGB/occluder evidence refused, despite manual left reference')
    engine._replay_state = refuse
    with pytest.raises(ValueError, match='right eye RGB'): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and len(owner.commits) == 2


@pytest.mark.parametrize('fault', ['native', 'analysis', 'target', 'unmanaged', 'source',
    'document', 'owner', 'epoch', 'proof', 'source-kind', 'original-source'])
def test_replay_rechecks_live_owner_source_face_and_capability(monkeypatch, fault):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(.3, .4, 'right'))
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


def test_unchanged_active_recipe_still_reaches_strict_complete_render(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    put(owner, .3, .4); REPLAY.replay_preset(engine, C.capture(engine))
    assert not owner.commits and calls[-1][1]['strict_local'] is True


@pytest.mark.parametrize('reference', ['left', 'right'])
def test_unmanaged_replay_cannot_silently_drop_dormant_manual_policy(monkeypatch, reference):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    engine._people_managed = lambda: False
    with pytest.raises(ValueError, match='规范人物'):
        REPLAY.replay_preset(engine, {C.FIELD: recipe(reference=reference)['recipe']})
    assert not owner.commits and not calls


def test_failed_render_restores_graph_and_existing_preset_history_rollback(monkeypatch):
    from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
    from lumaretouch_engine.preset_transaction import apply_with_rollback, PresetApplyError
    engine, initial, _, _, _ = replay_fixture(monkeypatch)
    owner = PeopleGraphOwner(initial.snapshot()); engine._people_owner = lambda: owner
    before_graph = owner.snapshot(); before = C.capture(engine); after = deepcopy(before)
    C.install(after, recipe(.3, .4, 'left')); calls = []
    def render(state, **kwargs):
        calls.append((deepcopy(state), kwargs))
        if len(calls) == 1: raise RuntimeError('complete target-render refusal')
        return {'event': 'frame'}
    engine._replay_state = render
    with pytest.raises(PresetApplyError) as error:
        apply_with_rollback(lambda state, **kwargs: REPLAY.replay_preset(engine, state, **kwargs),
            before, after, preset_id='eye-symmetry', emit=lambda event: None,
            invalidate=lambda: pytest.fail('Rollback must remain available'))
    assert error.value.rolled_back is True and len(calls) == 2
    assert calls[0][1]['strict_local'] is True and calls[1][1]['mode'] == 'preset_rollback'
    actual = owner.snapshot()
    assert actual['revision'] == before_graph['revision'] + 2 and owner.fence == 2
    assert {key: value for key, value in actual.items() if key != 'revision'} == {
        key: value for key, value in before_graph.items() if key != 'revision'}


def test_dormant_manual_policy_survives_project_history_without_changing_legacy_intent():
    from lumaretouch_engine import people_project as PROJECT
    old, _ = graph(); old = P.set_override(old, 'group', 'preserved', A.DEFORM, '/big_eye', .2)
    edited = P.set_override(old, 'face', FACE, C.OP, '/reference', 'right')
    source_proof = endpoint(old, 'target-document', scope='project')['source_proof']
    payload = {'people_graph': edited, 'source_proof': source_proof,
        'undo': [{'_people_state': old, 'source_proof': deepcopy(source_proof)}],
        'redo': [{'_people_state': edited, 'source_proof': deepcopy(source_proof)}]}
    restored = json.loads(json.dumps(payload, sort_keys=True, allow_nan=False)); PROJECT.validate_records(restored)
    assert restored == payload
    for state, reference in ((restored['people_graph'], 'right'),
            (restored['undo'][0]['_people_state'], 'auto'), (restored['redo'][0]['_people_state'], 'right')):
        materialized = A.recipes(resolve(P.check(state), FACE, A.defaults()))
        assert materialized[C.OP] == recipe(reference=reference)['recipe']
        assert not S.active(materialized[C.OP]) and materialized[A.DEFORM]['big_eye'] == .2
        assert state['faces'] == old['faces'] and state['links'] == old['links']


def test_no_new_pairwise_exclusion_or_legacy_conversion():
    state, _ = graph()
    for op, path, value in ((A.DEFORM, '/big_eye', .2), (PHILTRUM.OP, '/amount', -.3),
            (C.OP, '/horizontal', .4), (C.OP, '/size', .3), (C.OP, '/reference', 'left')):
        state = P.set_override(state, 'face', FACE, op, path, value)
    before = deepcopy(state); resolved = A.recipes(resolve(state, FACE, A.defaults()))
    A.validate_compatibility(resolved)
    assert resolved[C.OP] == recipe(.4, .3, 'left')['recipe'] and state == before
    # Existing independent chin-length/legacy conflict remains authoritative.
    state = P.set_override(state, 'face', FACE, LENGTH.OP, '/amount', .2)
    state = P.set_override(state, 'face', FACE, A.DEFORM, '/small_chin', -.3)
    with pytest.raises(ValueError, match='旧版小下巴'):
        A.validate_compatibility(A.recipes(resolve(state, FACE, A.defaults())))


def test_install_changes_only_transport_and_preserves_generic_derived_guard(monkeypatch):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    before = C.capture(engine); after = SC.apply_modules(before, {C.OP: recipe(.3, .4, 'left')})
    assert {key for key in after if before.get(key) != after[key]} == {C.FIELD, C.REQUESTED}
    assert after[C.TARGET] == before[C.TARGET] and after[C.OWNER] == before[C.OWNER]
    with pytest.raises(ValueError, match='合成来源'): C.install({**before, '_creative_base': {}}, recipe())
    with pytest.raises(SC.ScopeError): SC.check_derived_modules({C.OP: recipe()})
    with pytest.raises(ValueError): SC.apply_modules({}, {C.OP: recipe(.3, .4)})
    assert not owner.commits


def test_generic_preset_never_guesses_between_multiple_enabled_faces(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    other, _ = graph(face_id='neighbour'); owner.value['faces']['neighbour'] = other['faces']['neighbour']
    before = owner.snapshot(); state = C.capture(engine); C.install(state, recipe(.3, .4))
    with pytest.raises(ValueError, match='one explicit unambiguous enabled face'): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


def test_capture_authenticates_live_state_not_parked_row(monkeypatch):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, _, current = engine_fixture(monkeypatch)
    current['audit_marker'] = 'live'; engine._docs[0]['state'] = {'audit_marker': 'parked'}; seen = []
    def source_proof(row):
        seen.append(deepcopy(row['state'])); assert row['state']['audit_marker'] == 'live'
        return {'asset_sha256': ASSET, 'creative_source': None, 'original_sha256': ASSET}
    monkeypatch.setattr(I.SOURCE, 'row_proof', source_proof)
    assert C.params_of(C.capture(engine)) == recipe() and seen == [current]
    assert engine._docs[0]['state'] == {'audit_marker': 'parked'} and not owner.commits


@pytest.mark.parametrize('reuse_original', [False, True])
def test_derived_capture_requires_own_effective_analysis_not_original_donor(monkeypatch, reuse_original):
    from lumaretouch_engine import people_transfer_inventory as I
    engine, owner, original, current = engine_fixture(monkeypatch)
    derived = 'e' * 64; target, own = graph(derived); owner.value = target
    engine._people_source = lambda: {'sha256': derived, 'width': 640, 'height': 480}
    engine._people_cursors = {derived: FACE}
    engine._people_targets = {derived: {'scope': 'face', 'target_id': FACE,
        'face_ref': P.face_ref(target['faces'][FACE])}}
    engine._people_analyses = {ASSET: {FACE: original}, derived: {FACE: original if reuse_original else own}}
    current['_creative_base'] = {'fixture': 'derived baseline, not product pixels'}
    monkeypatch.setattr(I.SOURCE, 'row_proof', lambda row: {'asset_sha256': derived,
        'creative_source': {'sha256': derived, 'width': 640, 'height': 480}, 'original_sha256': ASSET})
    put(owner, .3, .4, 'auto'); captured = C.capture(engine)
    assert captured['_eye_symmetry_supported'] is (not reuse_original)
    if reuse_original:
        with pytest.raises(ValueError): C.params_of(captured)
    else:
        assert C.params_of(captured) == recipe(.3, .4)
        assert C.owner_identity(captured)['source_proof']['asset_sha256'] == derived
    with pytest.raises(ValueError, match='合成来源'): C.install(captured, recipe())
    assert not owner.commits


def test_batch_selection_accepts_only_strengths_and_closed_reference_policy():
    from lumaretouch_engine import people_batch_transfer as B
    state, _ = graph(); selected = {'source_ref': P.face_ref(state['faces'][FACE]),
        'selection': {C.OP: list(LEAVES)}, 'target_policy': 'confirmed_person_only'}
    assert B.options(selected, [C.OP], ASSET) == selected
    for path in ('/version', '/left', '/right', '/face_ref', '/landmarks', '/excluded',
            '/pixels', '/reference_eye', '/actual_reference', '/size_ratio', '/measured_level'):
        wrong = deepcopy(selected); wrong['selection'][C.OP] = [path]
        with pytest.raises(ValueError, match='scalar parameter leaves'): B.options(wrong, [C.OP], ASSET)


@pytest.mark.parametrize('reference', ['auto', 'left', 'right'])
@pytest.mark.parametrize('policy', ['explicit_face_map', 'confirmed_person_only'])
def test_transfer_only_selected_reference_policy_preserves_target_strengths_and_assets(reference, policy):
    from lumaretouch_engine import people_transfer_adapter as T
    from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed
    source, _ = graph(face_id='source-face'); target, _ = graph('e' * 64)
    for state, face_id in ((source, 'source-face'), (target, FACE)):
        state['persons']['confirmed-person'] = {'anonymous': True}
        state['links'] = [{'face_instance_id': face_id, 'person_id': 'confirmed-person',
            'state': 'confirmed', 'confirmation_revision': 0}]
    source = P.set_override(source, 'face', 'source-face', C.OP, '/reference', reference)
    for path, value in (('/horizontal', .6), ('/size', .2), ('/reference', 'left')):
        target = P.set_override(target, 'face', FACE, C.OP, path, value)
    target = P.set_override(target, 'face', FACE, A.DEFORM, '/big_eye', .2)
    owner_scope = 'project' if policy == 'confirmed_person_only' else None
    source_owner = endpoint(source, 'source', scope=owner_scope); target_owner = endpoint(target, 'target', scope=owner_scope)
    kwargs = {'source_document': source_owner['document'], 'target_document': target_owner['document'],
        'source_owner': source_owner, 'target_owner': target_owner}
    selection = {C.OP: ['/reference']}
    if policy == 'confirmed_person_only':
        payload = prepare_confirmed(source, target, P.face_ref(source['faces']['source-face']), 'e' * 64,
            selection, A.defaults(), **kwargs)
    else:
        payload = T.prepare(source, target, P.face_ref(source['faces']['source-face']),
            [P.face_ref(target['faces'][FACE])], selection, A.defaults(), **kwargs)
        payload['target_policy'] = policy
    candidate = T.candidate(payload, source, target, **kwargs)
    assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': '/reference', 'value': reference}]
    materialized = A.recipes(resolve(candidate, FACE, A.defaults()))
    assert materialized[C.OP] == recipe(.6, .2, reference)['recipe']
    assert materialized[A.DEFORM]['big_eye'] == .2
    assert candidate['faces'] == target['faces'] and candidate['links'] == target['links']
    assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
    changed = deepcopy(target_owner); changed['source_proof'] = {'asset_sha256': 'f' * 64,
        'creative_source': None, 'original_sha256': 'f' * 64}
    with pytest.raises(ValueError, match='owner, source or graph changed'):
        T.verify(payload, source, target, **{**kwargs, 'target_owner': changed})


@pytest.mark.parametrize('reference', ['auto', 'left', 'right'])
@pytest.mark.parametrize('policy', ['explicit_face_map', 'confirmed_person_only'])
@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('fault', [None, 'target-right-eye', 'copied-source-analysis'])
def test_each_full_target_remeasures_own_reference_and_requires_both_eyes(monkeypatch, reference, policy, derived, fault):
    """Actual batch routing/measurement/evidence, mocked full-render boundary.

    No native, TPS, raster rendering or photographic claim is made by this test.
    Different target eye proportions must resolve auto independently, and a
    manual left reference does not excuse right-eye RGB/occluder rejection.
    """
    from lumaretouch_engine import people_batch_transfer as B, people_transfer_inventory as I
    from lumaretouch_engine import full_candidate_render as FULL, eye_symmetry_runtime as R
    from lumaretouch_engine.people_render_runtime import verify_analysis
    from test_eye_symmetry_geometry_unrun import _fixture
    settings = {
        'source': (ASSET, 'source-face', 1.06, 1., 2.),
        'target-a': ('e' * 64, 'target-a-face', 1., 1.04, -3.),
        'target-b': ('f' * 64, 'target-b-face', 1.03, 1., 1.)}
    states = {}; analyses = {}; sources = {}; face_ids = {}
    for identity, (asset, face_id, left, right, difference) in settings.items():
        state, analysis = graph(asset, face_id)
        landmarks, rgb, excluded = _fixture(left_scale=left, right_scale=right, height_difference=difference)
        h, w = rgb.shape[:2]; evidence = state['faces'][face_id]['evidence']
        evidence.update(source_width=w, source_height=h,
            landmark_digest=sha256(landmarks.astype('<f4').tobytes()).hexdigest())
        analysis.update(evidence=deepcopy(evidence), landmarks=landmarks, excluded=excluded,
            skin=excluded * 0. + 1., face_skin=excluded * 0. + 1.)
        analysis['face_skin_observation'].update(producer_width=w, producer_height=h)
        if policy == 'confirmed_person_only':
            state['persons']['confirmed-person'] = {'anonymous': True}
            state['links'] = [{'face_instance_id': face_id, 'person_id': 'confirmed-person',
                'state': 'confirmed', 'confirmation_revision': 0}]
        states[identity] = state; analyses[identity] = analysis
        sources[identity] = rgb; face_ids[identity] = face_id
    for path, value in A.leaves(recipe(.5, .6, reference)['recipe']).items():
        states['source'] = P.set_override(states['source'], 'face', 'source-face', C.OP, path, value)
    source_measurement = R._measure(R.pixels(analyses['source']['landmarks'], sources['source'].shape[:2]))
    source_reference, source_scales, source_shifts = R._corrections(source_measurement, recipe(.5, .6, reference)['recipe'])
    assert source_reference == ('left' if reference == 'auto' else reference)
    for identity in ('target-a', 'target-b'):
        states[identity] = P.set_override(states[identity], 'face', face_ids[identity], A.DEFORM, '/big_eye', .2)
        states[identity]['faces'][face_ids[identity]]['local_assets']['target-only']['content_sha256'] = (
            '1' if identity == 'target-a' else '2') * 64
    if fault == 'target-right-eye':
        # An actual target-local occluder plane, not a forged visibility result.
        analysis = analyses['target-b']; lm = R.pixels(analysis['landmarks'], sources['target-b'].shape[:2])
        eye = lm[list(R.EYES['right'])]
        x0, y0 = (eye.min(0) - 12).astype(int); x1, y1 = (eye.max(0) + 13).astype(int)
        analysis['excluded'][y0:y1, x0:x1] = 1.
    elif fault == 'copied-source-analysis':
        analyses['target-b'] = analyses['source']
    owner = Owner(states['source'])
    rows = [{'document_id': identity, 'path': identity + '.jpg', 'state': {}} for identity in states]
    if derived:
        for row in rows[1:]: row['state']['_creative_base'] = {'fixture': row['document_id'] + ' immutable source'}
    def proof(state, identity):
        out = endpoint(state, identity, scope='project' if policy == 'confirmed_person_only' else None)
        if derived and identity != 'source':
            asset = state['faces'][face_ids[identity]]['asset_sha256']; h, w = sources[identity].shape[:2]
            out['source_proof']['creative_source'] = {'sha256': asset, 'width': w, 'height': h}
            out['source_proof']['original_sha256'] = '3' * 64
        return out
    versions = SimpleNamespace(workspace='workspace', version=lambda row:
        SimpleNamespace(document_id=row['document_id'], revision=2))
    batch = SimpleNamespace(versions=versions,
        documents=SimpleNamespace(rows=lambda: rows, current_index=lambda: 0, remember_current=lambda: None),
        target_indices=lambda docs: ([1, 2], []))
    engine = SimpleNamespace(_people_bind=lambda: None, _people_owner=lambda: owner,
        _batch_controller=lambda: batch, _document_versions=lambda: versions,
        _body_bank=lambda: pytest.fail('Eye symmetry does not acquire body coverage'))
    monkeypatch.setattr(B.V, 'row_snapshot', lambda actual, row: deepcopy(states[row['document_id']]))
    monkeypatch.setattr(I, 'proof', lambda actual, row, state: proof(state, row['document_id']))
    def verify(actual, row, state, expected):
        assert expected == proof(state, row['document_id']); return expected
    monkeypatch.setattr(I, 'verify', verify)
    monkeypatch.setattr(B.SOURCE, 'row_proof', lambda row: proof(states[row['document_id']], row['document_id'])['source_proof'])
    def verify_source(row, expected):
        assert expected == B.SOURCE.row_proof(row); return expected
    monkeypatch.setattr(B.SOURCE, 'verify_row', verify_source)
    expected_parameters = [{'operation_id': C.OP, 'parameter_path': path, 'value': value}
        for path, value in sorted(A.leaves(recipe(.5, .6, reference)['recipe']).items())]
    renders = []; measured = {}
    def render(actual, row, state, document_id, revision, *, people_graph):
        assert actual is engine and row['document_id'] == document_id
        assert state is row['state'] and revision == '2' and document_id != 'source'
        target = states[document_id]; face_id = face_ids[document_id]
        for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
            assert people_graph[key] == target[key]
        assert all(leaf in people_graph['overrides'] for leaf in target['overrides'])
        assert [leaf for leaf in people_graph['overrides'] if leaf not in target['overrides']] == [
            {'scope': 'face', 'target_id': face_id, **parameter} for parameter in expected_parameters]
        renders.append(document_id)
        analysis, rgb = analyses[document_id], sources[document_id]
        landmark = verify_analysis(people_graph['faces'][face_id], analysis, rgb.shape[:2])
        lm = R.pixels(landmark, rgb.shape[:2])
        # Use actual existing RGB/known-occluder evidence, never a mocked result.
        for side in ('left', 'right'):
            facts, *_ = R.evidence(lm, rgb, analysis['excluded'], side)
            if facts['size']['reason'] is not None:
                raise ValueError('Target-owned ' + side + ' eye refused: ' + facts['size']['reason'])
        candidate_recipe = A.recipes(resolve(people_graph, face_id, A.defaults()))[C.OP]
        own = R._measure(lm); selected, scales, shifts = R._corrections(own, candidate_recipe)
        expected_reference = ('right' if document_id == 'target-a' else 'left') if reference == 'auto' else reference
        assert selected == expected_reference and scales[selected] == 1.
        assert shifts['left'] == pytest.approx(-.25 * own['height_difference'])
        assert shifts['right'] == pytest.approx(.25 * own['height_difference'])
        if reference == 'auto': assert scales['left' if selected == 'right' else 'right'] > 1.
        if document_id == 'target-a':
            assert shifts != source_shifts and scales != source_scales
            if reference == 'auto': assert selected != source_reference
        measured[document_id] = (selected, scales, shifts)
        return None, {'fixture': 'actual target evidence and measurements, mocked complete render'}
    monkeypatch.setattr(FULL, 'render', render); plans = []
    def freeze(workspace, source_id, revision, path, modules, params, target_policy, targets, rejected):
        plans.append(targets)
        return SimpleNamespace(modules=modules, token='fixture-token', workspace=workspace, expires_ns=1)
    replies = []; controller = SimpleNamespace(store=SimpleNamespace(create=freeze), _source=lambda plan: {},
        emit=lambda event: None, emit_result=lambda request, body: replies.append(body))
    request = {'cmd': 'batch', 'action': 'preflight', 'request_id': 'fixture-eye-symmetry',
        'docs': ['target-a', 'target-b'], 'module_scope': [C.OP], 'people_transfer': {
            'source_ref': P.face_ref(states['source']['faces']['source-face']), 'selection': {C.OP: list(LEAVES)},
            'target_policy': 'explicit_face_map', 'source': proof(states['source'], 'source'), 'targets': [
                {'target': proof(states[identity], identity),
                 'target_refs': [P.face_ref(states[identity]['faces'][face_ids[identity]])]}
                for identity in ('target-a', 'target-b')]}}
    if policy == 'confirmed_person_only':
        request['people_transfer'] = {key: value for key, value in request['people_transfer'].items()
            if key not in ('source', 'targets')}
        request['people_transfer']['target_policy'] = policy
    before = deepcopy(states); B.preflight(engine, controller, request)
    assert states == before and not owner.commits and renders == ['target-a', 'target-b']
    result = replies[-1]
    assert (result['ok'], result['blocked']) == ((1, 1) if fault else (2, 0))
    assert set(measured) == ({'target-a'} if fault else {'target-a', 'target-b'})
    for index, identity in enumerate(('target-a', 'target-b')):
        payload = result['targets'][index]['people_transfer']
        if fault and identity == 'target-b':
            assert payload is None and plans[0][index].people_json is None
            assert result['targets'][index]['blocked']
        else:
            assert payload['parameters'] == expected_parameters
            assert payload['target_refs'] == [P.face_ref(states[identity]['faces'][face_ids[identity]])]
            assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
            assert not any(key in payload for key in ('pixels', 'actual_reference', 'reference_eye', 'size_ratio', 'measured_level'))
            assert json.loads(plans[0][index].people_json) == payload
