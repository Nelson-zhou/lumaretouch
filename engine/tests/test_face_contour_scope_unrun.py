"""AUTHORED / UNRUN: bilateral contour presets and source-local face transfer.

Synthetic observations and mocked native/full-render boundaries prove intended
contracts only when run. They are not inference, pixel, Rust or photographic
acceptance evidence. No product imports, collection, tests or builds were run
while authoring this file.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest

from lumaretouch_engine import face_contour_scope as C, face_contour_state as S
from lumaretouch_engine import face_contour_native as N
from lumaretouch_engine import people_state as P, people_algorithms as A, people_scope as REPLAY, scope as SC
from lumaretouch_engine import skin_colour_scope as COLOUR
from lumaretouch_engine.workflow_ports import WorkflowPortsMixin
from test_skin_colour_scope_unrun import (ASSET, FACE, Owner, graph, endpoint,
    engine_fixture as colour_engine_fixture, isolate_other_captures)

CONTROLS = ('temple', 'cheekbone', 'jaw')
SIDES = ('left', 'right')
LEAVES = tuple('/' + key + '/' + leaf for key in CONTROLS for leaf in ('linked', *SIDES))


def recipe(**controls):
    return {'recipe': {'version': 1, **{key: {'linked': True, 'left': 0., 'right': 0.}
        for key in CONTROLS}, **deepcopy(controls)}}


def bilateral(left=.35, right=-.2, *, linked=False):
    return {'linked': linked, 'left': left, 'right': right}


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
        if fail: raise RuntimeError('authored target-render refusal')
        return {'event': 'frame', 'render_ms': 0}
    engine._replay_state = replay
    return engine, owner, analysis, current, calls


def test_distinct_operation_keeps_legacy_four_geometry_slots_and_derived_guard():
    assert C.OP == 'lnx.face_contour.v1'
    assert A.GEOMETRY == ('lnx.brow_shape.v1', 'lnx.nose_shape.v1', 'lnx.eye_shape.v1', 'lnx.mouth_shape.v1')
    assert C.OP not in A.GEOMETRY and C.OP not in SC.DERIVED_PARAMETER_OPS
    assert SC.MODULES[C.OP]['read'] is C.params_of
    assert SC.MODULES[C.OP]['write'] is C.install
    assert SC.MODULES[C.OP]['state_fields'] == (C.FIELD,)
    assert SC.MODULES[C.OP]['single_face'] is True
    assert A.defaults()[C.OP] == {path: True if path.endswith('/linked') else 0. for path in LEAVES}
    assert S.neutral() == recipe()['recipe'] and not S.active(S.neutral())
    assert set(A.defaults()[C.OP]) == set(LEAVES)


@pytest.mark.parametrize('key', CONTROLS)
@pytest.mark.parametrize('side', SIDES)
@pytest.mark.parametrize('amount', [-1., -.5, 0., .5, 1.])
def test_all_six_signed_scalars_and_three_link_flags_round_trip(key, side, amount):
    values = bilateral(); values[side] = amount
    params = recipe(**{key: values})
    assert C.check_params(params) == params and SC.check_params(C.OP, params) == params


@pytest.mark.parametrize('value', [True, False, None, '0.5', float('nan'), float('inf'), -1.01, 1.01, 10**1000])
@pytest.mark.parametrize('key', CONTROLS)
@pytest.mark.parametrize('side', SIDES)
def test_invalid_scalar_rejects_without_any_context_mutation(monkeypatch, key, side, value):
    engine, _, _, _ = engine_fixture(monkeypatch)
    state = C.capture(engine); before = deepcopy(state); params = recipe()
    params['recipe'][key][side] = value
    with pytest.raises(ValueError): C.install(state, params)
    assert state == before


@pytest.mark.parametrize('key', ['face_ref', 'owner', 'source', 'face_skin', 'excluded', 'landmarks',
    'analysis', 'mesh', 'control_points', 'displacement', 'mask', 'coverage', 'support', 'body_ref', 'ai', 'model_3d'])
def test_portable_recipe_rejects_source_copy_and_non_scalar_fields(key):
    params = recipe(temple=bilateral())
    with pytest.raises(ValueError): C.check_params({**params, key: {}})
    params['recipe'][key] = {}
    with pytest.raises(ValueError): C.check_params(params)
    params = recipe(); params['recipe']['jaw'][key] = {}
    with pytest.raises(ValueError): C.check_params(params)


@pytest.mark.parametrize('fault', ['null', 'missing-version', 'bool-version', 'new-version',
    'missing-control', 'missing-side', 'non-bool-link'])
def test_recipe_requires_exact_versioned_bilateral_shape(fault):
    params = recipe()
    if fault == 'null': params['recipe'] = None
    elif fault == 'missing-version': del params['recipe']['version']
    elif fault == 'bool-version': params['recipe']['version'] = True
    elif fault == 'new-version': params['recipe']['version'] = 2
    elif fault == 'missing-control': del params['recipe']['cheekbone']
    elif fault == 'missing-side': del params['recipe']['jaw']['right']
    else: params['recipe']['temple']['linked'] = 1
    with pytest.raises(ValueError): C.check_params(params)


def test_portable_preset_keeps_asymmetric_values_even_when_relinked():
    params = recipe(temple=bilateral(linked=True), cheekbone=bilateral(-.4, .7), jaw=bilateral(.5, -.6))
    original = {'schema': SC.PRESET_SCHEMA, 'id': 'contour-bilateral', 'name': 'Contour bilateral',
        'kind': 'portrait', 'modules': {C.OP: params}}
    portable = json.loads(SC.dump_preset(original))
    assert SC.validate_preset(portable)['modules'] == {C.OP: params}
    assert set(portable['modules'][C.OP]['recipe']) == {'version', *CONTROLS}
    assert all(set(portable['modules'][C.OP]['recipe'][key]) == {'linked', *SIDES} for key in CONTROLS)
    assert A.leaves(portable['modules'][C.OP]['recipe']) == A.leaves(params['recipe'])


@pytest.mark.parametrize('key', CONTROLS)
def test_relink_does_not_copy_one_side_and_next_linked_adjustment_is_explicit(key):
    original = recipe(**{key: bilateral()})['recipe']
    relinked = S.link(original, key, True)
    assert original[key] == bilateral() and relinked[key] == bilateral(linked=True)
    assert S.adjust(relinked, key, 'right', -.6)[key] == bilateral(-.6, -.6, linked=True)


def test_workflow_capture_is_intent_only_and_reuses_existing_owner_proof(monkeypatch):
    engine, owner, analysis, current = engine_fixture(monkeypatch); isolate_other_captures(monkeypatch)
    params = recipe(temple=bilateral(), cheekbone=bilateral(-.4, .2), jaw=bilateral(.5, -.1))
    for path, value in A.leaves(params['recipe']).items():
        owner.value = P.set_override(owner.value, 'face', FACE, C.OP, path, value)
    captured = WorkflowPortsMixin._people_preset_capture(engine)
    portable = SC.params_of(captured, [C.OP])
    assert portable == {C.OP: params} and json.loads(json.dumps(portable)) == portable
    assert captured[C.TARGET] == P.face_ref(owner.value['faces'][FACE])
    assert captured['_face_contour_supported'] is True and captured[C.REQUESTED] is False
    assert C.owner_identity(captured) == {'document_id': 'target-document', 'epoch': 'workspace',
        'people_scope': 'project', 'source_proof': {'asset_sha256': ASSET,
            'creative_source': None, 'original_sha256': ASSET}}
    assert set(captured[C.OWNER]) == {'document', 'people_scope', 'state_revision',
        'association_revision', 'graph_sha256', 'source_proof'}
    assert 'face_skin' not in captured and 'landmarks' not in captured
    assert engine._people_analyses[ASSET][FACE] is analysis and current == {}


@pytest.mark.parametrize('fault', ['face-skin', 'observation', 'excluded', 'ref', 'model',
    'landmark-bytes', 'landmark-count', 'synthetic', 'dimensions', 'donor-analysis'])
def test_capture_requires_own_authenticated_skin_and_actual_478_landmarks(monkeypatch, fault):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    if fault == 'face-skin': analysis['face_skin'] = None
    elif fault == 'observation': analysis.pop('face_skin_observation')
    elif fault == 'excluded': analysis['excluded'] = None
    elif fault == 'ref': analysis['face_ref']['analysis_revision'] += 1
    elif fault == 'model': analysis['face_skin_observation']['semantic_model_sha256'] = 'f' * 64
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
    assert captured['_face_contour_supported'] is False
    with pytest.raises(ValueError): C.install(captured, recipe(jaw=bilateral()))
    assert not owner.commits


@pytest.mark.parametrize('fault', ['no-cursor', 'group-target', 'stale-target', 'disabled', 'unmanaged', 'no-document'])
def test_selection_needs_exact_owner_and_face_not_just_cursor(monkeypatch, fault):
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


def test_neutral_reset_needs_same_owner_but_not_stale_support_or_native(monkeypatch):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    for path, value in A.leaves(recipe(temple=bilateral(), jaw=bilateral(.5, -.6))['recipe']).items():
        owner.value = P.set_override(owner.value, 'face', FACE, C.OP, path, value)
    monkeypatch.setattr(N, 'available', lambda: False)
    with pytest.raises(ValueError, match='Rust'): C.install(C.capture(engine), recipe(cheekbone=bilateral()))
    analysis['excluded'] = None
    state = C.capture(engine); C.install(state, recipe()); REPLAY.replay_preset(engine, state)
    assert {leaf['parameter_path']: leaf['value'] for leaf in owner.value['overrides']
        if leaf['operation_id'] == C.OP} == A.defaults()[C.OP]
    assert calls[-1][1]['strict_local'] is True


def test_install_changes_only_ephemeral_recipe_and_preserves_derived_refusal(monkeypatch):
    engine, _, _, _ = engine_fixture(monkeypatch)
    before = C.capture(engine); after = SC.apply_modules(before, {C.OP: recipe(jaw=bilateral())})
    assert {key for key in after if before.get(key) != after[key]} == {C.FIELD, C.REQUESTED}
    assert after[C.TARGET] == before[C.TARGET] and after[C.OWNER] == before[C.OWNER]
    with pytest.raises(ValueError, match='合成来源'): C.install({**before, '_creative_base': {}}, recipe())
    with pytest.raises(SC.ScopeError): SC.check_derived_modules({C.OP: recipe()})
    with pytest.raises(ValueError): SC.apply_modules({}, {C.OP: recipe(jaw=bilateral())})


@pytest.mark.parametrize('key', CONTROLS)
def test_replay_uses_existing_people_owner_and_preserves_other_operations(monkeypatch, key):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, COLOUR.OP, '/tint', -.25)
    before = owner.snapshot(); params = recipe(**{key: bilateral()})
    state = C.capture(engine); C.install(state, params); REPLAY.replay_preset(engine, state, mode='preset')
    after = owner.snapshot()
    for field in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
        assert after[field] == before[field]
    assert all(row in after['overrides'] for row in before['overrides'])
    added = [row for row in after['overrides'] if row not in before['overrides']]
    assert {(leaf['parameter_path'], leaf['value']) for leaf in added} == {
        ('/' + key + '/linked', False), ('/' + key + '/left', .35), ('/' + key + '/right', -.2)}
    assert all(leaf['scope'] == 'face' and leaf['target_id'] == FACE and leaf['operation_id'] == C.OP for leaf in added)
    assert len(calls) == len(owner.commits) == 1 and calls[0][1]['strict_local'] is True
    assert engine._people_analyses[ASSET][FACE] is analysis


@pytest.mark.parametrize('fault', ['native', 'analysis', 'target', 'unmanaged', 'source', 'document', 'owner', 'epoch', 'proof', 'source-kind'])
def test_replay_rechecks_target_and_owner_instead_of_captured_flags(monkeypatch, fault):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(temple=bilateral()))
    if fault == 'native': monkeypatch.setattr(N, 'available', lambda: False)
    elif fault == 'analysis': analysis['excluded'] = None
    elif fault == 'target': engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    elif fault == 'unmanaged': engine._people_managed = lambda: False
    elif fault == 'source': engine._people_source = lambda: {'sha256': 'e' * 64, 'width': 640, 'height': 480}
    elif fault == 'document': engine._docs[0]['document_id'] = 'another-document'
    elif fault == 'owner': engine._docs[0]['copy_number'] = 1
    elif fault == 'epoch': engine._document_versions().workspace = 'another-workspace'
    elif fault == 'proof': state.pop(C.OWNER)
    else:
        state[C.OWNER]['source_proof']['creative_source'] = {'sha256': ASSET, 'width': 640, 'height': 480}
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert not owner.commits and not calls


def test_explicitly_switching_to_another_same_source_face_rejects_old_capture(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(jaw=bilateral()))
    other, analysis = graph(face_id='another-face')
    owner.value['faces']['another-face'] = other['faces']['another-face']
    owner.value['faces'][FACE]['enabled'] = False
    engine._people_analyses[ASSET]['another-face'] = analysis
    engine._people_cursors[ASSET] = 'another-face'
    engine._people_targets[ASSET] = {'scope': 'face', 'target_id': 'another-face', 'face_ref': P.face_ref(other['faces']['another-face'])}
    before = owner.snapshot()
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


def test_unchanged_active_contour_still_requires_strict_renderer(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/cheekbone/right', -.25)
    REPLAY.replay_preset(engine, C.capture(engine))
    assert not owner.commits and calls[-1][1]['strict_local'] is True


def test_link_only_neutral_change_preserves_zero_sides_and_uses_canonical_owner(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(temple=bilateral(0., 0.)))
    assert not S.active(state[C.FIELD])
    REPLAY.replay_preset(engine, state)
    assert [row for row in owner.value['overrides'] if row['operation_id'] == C.OP] == [
        {'scope': 'face', 'target_id': FACE, 'operation_id': C.OP,
         'parameter_path': '/temple/linked', 'value': False}]
    assert calls[-1][1]['strict_local'] is True


def test_failed_render_rolls_back_canonical_intent_and_outer_preset_rollback_can_replay(monkeypatch):
    from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
    from lumaretouch_engine.preset_transaction import apply_with_rollback, PresetApplyError
    engine, initial, _, _, _ = replay_fixture(monkeypatch)
    owner = PeopleGraphOwner(initial.snapshot()); engine._people_owner = lambda: owner
    before_graph = owner.snapshot(); before = C.capture(engine); after = deepcopy(before)
    C.install(after, recipe(temple=bilateral(), cheekbone=bilateral(-.3, .5)))
    calls = []
    def render(state, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1: raise RuntimeError('authored target-render refusal')
        return {'event': 'frame'}
    engine._replay_state = render
    with pytest.raises(PresetApplyError) as error:
        apply_with_rollback(lambda state, **kwargs: REPLAY.replay_preset(engine, state, **kwargs),
            before, after, preset_id='contour', emit=lambda event: None,
            invalidate=lambda: pytest.fail('Rollback must remain available'))
    assert error.value.rolled_back is True and len(calls) == 2
    actual = owner.snapshot()
    assert actual['revision'] == before_graph['revision'] + 2 and owner.fence == 2
    assert {key: value for key, value in actual.items() if key != 'revision'} == {
        key: value for key, value in before_graph.items() if key != 'revision'}


def test_multiple_enabled_faces_are_not_guessed_by_generic_preset(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    other, _ = graph(face_id='neighbour-face'); owner.value['faces']['neighbour-face'] = other['faces']['neighbour-face']
    before = owner.snapshot(); state = C.capture(engine); C.install(state, recipe(jaw=bilateral()))
    with pytest.raises(ValueError, match='one explicit unambiguous enabled face'): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


def test_unrelated_replay_stays_usable_without_contour_target_or_document(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    engine._people_targets.clear(); engine._docs.clear()
    REPLAY.replay_preset(engine, {})
    assert not owner.commits and len(calls) == 1 and C.FIELD not in calls[0][0]


def test_people_selection_accepts_nine_intent_leaves_not_version_or_support():
    from lumaretouch_engine import people_batch_transfer as B
    value, _ = graph(); selected = {'source_ref': P.face_ref(value['faces'][FACE]),
        'selection': {C.OP: list(LEAVES)}, 'target_policy': 'confirmed_person_only'}
    assert B.options(selected, [C.OP], ASSET) == selected
    for path in ('/version', '/face_ref', '/face_skin', '/landmarks', '/analysis', '/mask', '/control_points', '/coverage'):
        wrong = deepcopy(selected); wrong['selection'][C.OP] = [path]
        with pytest.raises(ValueError, match='scalar parameter leaves'): B.options(wrong, [C.OP], ASSET)


@pytest.mark.parametrize('target_policy', ['explicit_face_map', 'confirmed_person_only'])
def test_selected_link_and_side_transfer_preserves_other_target_values_and_owner_fences(target_policy):
    from lumaretouch_engine import people_transfer_adapter as T
    from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed
    source, _ = graph(face_id='source-face'); target, _ = graph('e' * 64)
    for value, face_id in ((source, 'source-face'), (target, FACE)):
        value['persons']['confirmed-person'] = {'anonymous': True}
        value['links'] = [{'face_instance_id': face_id, 'person_id': 'confirmed-person',
            'state': 'confirmed', 'confirmation_revision': 0}]
    source = P.set_override(source, 'face', 'source-face', C.OP, '/temple/linked', True)
    source = P.set_override(source, 'face', 'source-face', C.OP, '/temple/left', -.4)
    source = P.set_override(source, 'face', 'source-face', C.OP, '/temple/right', .8)
    target = P.set_override(target, 'face', FACE, C.OP, '/temple/linked', False)
    target = P.set_override(target, 'face', FACE, C.OP, '/temple/right', .2)
    scope = 'project' if target_policy == 'confirmed_person_only' else None
    source_owner = endpoint(source, 'source', scope=scope); target_owner = endpoint(target, 'target', scope=scope)
    kwargs = {'source_document': source_owner['document'], 'target_document': target_owner['document'],
        'source_owner': source_owner, 'target_owner': target_owner}
    selection = {C.OP: ['/temple/linked', '/temple/left']}
    if target_policy == 'confirmed_person_only':
        payload = prepare_confirmed(source, target, P.face_ref(source['faces']['source-face']), 'e' * 64,
            selection, A.defaults(), **kwargs)
    else:
        payload = T.prepare(source, target, P.face_ref(source['faces']['source-face']),
            [P.face_ref(target['faces'][FACE])], selection, A.defaults(), **kwargs)
        payload['target_policy'] = target_policy
    candidate = T.candidate(payload, source, target, **kwargs)
    assert payload['parameters'] == [
        {'operation_id': C.OP, 'parameter_path': '/temple/left', 'value': -.4},
        {'operation_id': C.OP, 'parameter_path': '/temple/linked', 'value': True}]
    assert {leaf['parameter_path']: leaf['value'] for leaf in candidate['overrides']
        if leaf['operation_id'] == C.OP} == {'/temple/linked': True, '/temple/left': -.4, '/temple/right': .2}
    assert candidate['faces'] == target['faces'] and candidate['links'] == target['links']
    changed = deepcopy(target_owner); changed['source_proof'] = {'asset_sha256': 'f' * 64,
        'creative_source': None, 'original_sha256': 'f' * 64}
    with pytest.raises(ValueError, match='owner, source or graph changed'):
        T.verify(payload, source, target, **{**kwargs, 'target_owner': changed})


@pytest.mark.parametrize('target_policy', ['explicit_face_map', 'confirmed_person_only'])
@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('refused_target', [None, 'target-b'])
def test_each_different_target_uses_its_own_full_source_renderer_and_refusal(monkeypatch, target_policy, derived, refused_target):
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
    params = recipe(temple=bilateral(.2, -.4), cheekbone=bilateral(-.3, .5), jaw=bilateral(.6, -.1))
    for path, value in A.leaves(params['recipe']).items():
        source = P.set_override(source, 'face', 'source-face', C.OP, path, value)
    states['source'] = source
    for identity in ('target-a', 'target-b'):
        states[identity] = P.set_override(states[identity], 'face', face_ids[identity], COLOUR.OP, '/tint', -.2)
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
        _body_bank=lambda: pytest.fail('Contour does not acquire body coverage'))
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
            raise ValueError('Target-owned contour renderer refused spatial or photometric support')
        return None, {'fixture': 'routing only'}
    monkeypatch.setattr(FULL, 'render', render)
    plans = []
    def freeze(workspace, source_id, revision, path, modules, params, policy, targets, rejected):
        plans.append(targets)
        return SimpleNamespace(modules=modules, token='fixture-token', workspace=workspace, expires_ns=1)
    replies = []; controller = SimpleNamespace(store=SimpleNamespace(create=freeze), _source=lambda plan: {},
        emit=lambda event: None, emit_result=lambda request, body: replies.append(body))
    request = {'cmd': 'batch', 'action': 'preflight', 'request_id': 'fixture-contour',
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
            assert 'Target-owned contour renderer refused' in result['targets'][index]['blocked']
        else:
            assert payload['parameters'] == expected_parameters
            assert payload['target_refs'] == [P.face_ref(states[identity]['faces'][face_ids[identity]])]
            assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
            assert not any('coverage' in key or 'support' in key for key in payload)
            assert json.loads(plans[0][index].people_json) == payload
