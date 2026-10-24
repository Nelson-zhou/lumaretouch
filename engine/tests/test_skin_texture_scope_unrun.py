"""AUTHORED / UNRUN: scalar-only face-skin texture/clarity preset and transfer contracts.

Synthetic observation fixtures and mocked native/full-render boundaries test
intended routing, not real inference, Rust execution, pixels or acceptance.
No product imports, collection, execution, build or typecheck ran while authoring.
"""
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest

from lumaretouch_engine import skin_texture_scope as C, skin_texture_state as S
from lumaretouch_engine import skin_texture_native as N
from lumaretouch_engine import skin_colour_scope as COLOUR, skin_finish_scope as FINISH
from lumaretouch_engine import people_state as P, people_algorithms as A, people_scope as REPLAY, scope as SC
from lumaretouch_engine.workflow_ports import WorkflowPortsMixin
from test_skin_colour_scope_unrun import (ASSET, FACE, Owner, graph, endpoint,
    engine_fixture as colour_engine_fixture, replay_fixture as colour_replay_fixture,
    isolate_other_captures)


def recipe(texture=0., clarity=0.):
    return {'recipe': {'version': 1, 'texture': texture, 'clarity': clarity}}


def engine_fixture(monkeypatch):
    value = colour_engine_fixture(monkeypatch)
    monkeypatch.setattr(N, 'available', lambda: True)
    return value


def replay_fixture(monkeypatch, *, fail=False):
    value = colour_replay_fixture(monkeypatch, fail=fail)
    monkeypatch.setattr(N, 'available', lambda: True)
    return value


def test_registration_is_two_distinct_scalars_and_keeps_generic_derived_guard():
    assert C.OP == 'lnx.skin_texture.v1' and C.OP not in (COLOUR.OP, FINISH.OP)
    assert SC.MODULES[C.OP]['read'] is C.params_of
    assert SC.MODULES[C.OP]['write'] is C.install
    assert SC.MODULES[C.OP]['single_face'] is True
    assert SC.MODULES[C.OP]['state_fields'] == (C.FIELD,)
    assert C.OP not in SC.DERIVED_PARAMETER_OPS
    assert A.defaults()[C.OP] == {'/texture': 0., '/clarity': 0.}
    assert not hasattr(C, 'COVERAGE')
    for texture in (-1., -.4, 0., .4, 1.):
        for clarity in (0., .4, 1.):
            assert SC.check_params(C.OP, recipe(texture, clarity)) == recipe(texture, clarity)
    assert S.neutral() == recipe()['recipe'] and not S.active(S.neutral())
    assert S.active(recipe(0., .1)['recipe']) and S.active(recipe(-.1, 0.)['recipe'])


@pytest.mark.parametrize('value', [True, False, None, '0.5', float('nan'), float('inf'), -1.01, 1.01, 10**1000])
def test_invalid_signed_texture_does_not_mutate_context(monkeypatch, value):
    engine, _, _, _ = engine_fixture(monkeypatch); state = C.capture(engine); before = deepcopy(state)
    with pytest.raises(ValueError): C.install(state, recipe(value))
    assert state == before


@pytest.mark.parametrize('value', [True, False, None, '0.5', float('nan'), float('inf'), -.01, 1.01, 10**1000])
def test_invalid_unsigned_clarity_does_not_mutate_context(monkeypatch, value):
    engine, _, _, _ = engine_fixture(monkeypatch); state = C.capture(engine); before = deepcopy(state)
    with pytest.raises(ValueError): C.install(state, recipe(.2, value))
    assert state == before


@pytest.mark.parametrize('key', ['face_ref', 'body_ref', 'mask', 'face_skin', 'excluded',
    'landmarks', 'source', 'detail', 'detail_bands', 'source_detail', 'coarse_contrast', 'coverage', 'support', 'whole_body',
    'amount', 'enabled', 'radius', 'temperature', 'tint', 'whitening', 'rosiness', 'hair_gloss', 'lip_gloss'])
def test_portable_texture_rejects_support_body_and_other_algorithm_fields(key):
    with pytest.raises(ValueError): C.check_params({**recipe(.3), key: {}})
    params = recipe(.3); params['recipe'][key] = {}
    with pytest.raises(ValueError): C.check_params(params)


@pytest.mark.parametrize('params', [{}, {'recipe': None}, {'recipe': {'version': 1}},
    {'recipe': {'version': 1, 'texture': .2}}, {'recipe': {'version': 1, 'clarity': .3}},
    {'recipe': {'texture': .2, 'clarity': .3}},
    {'recipe': {'version': True, 'texture': .2, 'clarity': .3}}, {'recipe': {'version': 2, 'texture': .2, 'clarity': .3}}])
def test_portable_texture_requires_exact_versioned_recipe(params):
    with pytest.raises(ValueError): C.check_params(params)


def test_portable_preset_round_trip_contains_exact_recipe_and_no_target_state():
    original = {'schema': SC.PRESET_SCHEMA, 'id': 'face-texture-clarity',
        'name': 'Face texture and clarity', 'kind': 'portrait',
        'modules': {C.OP: recipe(-.4, .3)}}
    checked = SC.validate_preset(original)
    assert checked['modules'] == original['modules']
    portable = json.loads(SC.dump_preset(original))
    assert SC.validate_preset(portable)['modules'] == {C.OP: recipe(-.4, .3)}
    assert set(portable['modules'][C.OP]) == {'recipe'}
    assert set(portable['modules'][C.OP]['recipe']) == {'version', 'texture', 'clarity'}


def test_workflow_capture_exports_only_texture_scalars_and_keeps_other_skin_parameters(monkeypatch):
    engine, owner, analysis, current = engine_fixture(monkeypatch); isolate_other_captures(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/texture', -.45)
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/clarity', .35)
    owner.value = P.set_override(owner.value, 'face', FACE, COLOUR.OP, '/tint', -.2)
    owner.value = P.set_override(owner.value, 'face', FACE, FINISH.OP, '/whitening', .25)
    from lumaretouch_engine import skin_finish_native
    monkeypatch.setattr(skin_finish_native, 'available', lambda: True)
    captured = WorkflowPortsMixin._people_preset_capture(engine)
    portable = SC.params_of(captured, [C.OP, COLOUR.OP, FINISH.OP])
    assert portable[C.OP] == recipe(-.45, .35)
    assert portable[COLOUR.OP]['recipe']['tint'] == -.2
    assert portable[FINISH.OP]['recipe']['whitening'] == .25
    assert captured[C.TARGET] == P.face_ref(owner.value['faces'][FACE])
    assert captured['_skin_texture_supported'] is True and captured[C.REQUESTED] is False
    assert json.loads(json.dumps(portable[C.OP])) == recipe(-.45, .35)
    assert 'face_skin' not in captured and '_skin_texture_preset_coverage' not in captured
    assert engine._people_analyses[ASSET][FACE] is analysis and current == {}


def test_capture_never_requests_body_bank_or_reusable_detail_support(monkeypatch):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/texture', .4)
    engine._body_bank = lambda: pytest.fail('Face-only texture must not acquire a body bank')
    captured = C.capture(engine)
    assert set(captured) == {C.FIELD, C.TARGET, C.REQUESTED, '_skin_texture_supported',
        '_skin_texture_native_available', '_skin_texture_refusal'}
    assert C.params_of(captured) == recipe(.4)


@pytest.mark.parametrize('fault', ['merged-skin', 'observation', 'excluded', 'ref', 'model',
    'landmarks', 'synthetic', 'dimensions', 'donor-analysis'])
def test_capture_requires_own_real_selected_face_observation(monkeypatch, fault):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    if fault == 'merged-skin': analysis['face_skin'] = None
    elif fault == 'observation': analysis.pop('face_skin_observation')
    elif fault == 'excluded': analysis['excluded'] = None
    elif fault == 'ref': analysis['face_ref']['analysis_revision'] += 1
    elif fault == 'model': analysis['face_skin_observation']['semantic_model_sha256'] = 'f' * 64
    elif fault == 'landmarks': analysis['landmarks'][0, 0] = .8
    elif fault == 'synthetic':
        owner.value['faces'][FACE]['evidence']['status'] = 'synthetic'
        analysis['evidence']['status'] = 'synthetic'
    elif fault == 'dimensions': engine._people_source = lambda: {'sha256': ASSET, 'width': 641, 'height': 480}
    else: engine._people_analyses[ASSET] = {'different-person': analysis}
    state = C.capture(engine)
    assert state['_skin_texture_supported'] is False
    with pytest.raises(ValueError): C.install(state, recipe(.2))
    assert not owner.commits


@pytest.mark.parametrize('fault', ['cursor', 'group', 'stale', 'disabled', 'unmanaged', 'source'])
def test_capture_requires_explicit_enabled_current_source_target_even_for_neutral(monkeypatch, fault):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    if fault == 'cursor': engine._people_cursors.clear()
    elif fault == 'group': engine._people_targets[ASSET] = {'scope': 'group', 'target_id': 'preserved'}
    elif fault == 'stale': engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    elif fault == 'disabled': owner.value['faces'][FACE]['enabled'] = False
    elif fault == 'unmanaged': engine._people_managed = lambda: False
    else: engine._people_source = lambda: {'sha256': 'e' * 64, 'width': 640, 'height': 480}
    state = C.capture(engine)
    assert state[C.TARGET] is None
    with pytest.raises(ValueError): C.params_of(state)
    with pytest.raises(ValueError): C.install(state, recipe())


def test_native_refusal_allows_exact_target_neutral_reset_without_stale_support(monkeypatch):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/texture', -.6)
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/clarity', .4)
    monkeypatch.setattr(N, 'available', lambda: False)
    state = C.capture(engine)
    with pytest.raises(ValueError, match='Rust'): C.install(state, recipe(.2))
    with pytest.raises(ValueError, match='Rust'): C.install(state, recipe(0., .2))
    analysis['excluded'] = None
    state = C.capture(engine); C.install(state, recipe())
    REPLAY.replay_preset(engine, state)
    assert {leaf['parameter_path']: leaf['value'] for leaf in owner.value['overrides']
        if leaf['operation_id'] == C.OP} == {'/texture': 0., '/clarity': 0.}
    assert calls[-1][1]['strict_local'] is True


def test_install_changes_only_texture_transport_and_never_generic_derived_admission(monkeypatch):
    engine, _, _, _ = engine_fixture(monkeypatch)
    before = C.capture(engine); after = SC.apply_modules(before, {C.OP: recipe(-.3)})
    assert {key for key in after if before.get(key) != after[key]} == {C.FIELD, C.REQUESTED}
    assert after[C.TARGET] == before[C.TARGET]
    with pytest.raises(ValueError, match='合成来源'): C.install({**before, '_creative_base': {}}, recipe(.3))
    with pytest.raises(SC.ScopeError): SC.check_derived_modules({C.OP: recipe()})
    with pytest.raises(ValueError): SC.apply_modules({}, {C.OP: recipe(.3)})


@pytest.mark.parametrize('texture,clarity', [(-.6, 0.), (.6, 0.), (0., .4), (-.6, .4)])
def test_replay_consumes_only_texture_and_clarity_in_existing_people_owner(monkeypatch, texture, clarity):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, COLOUR.OP, '/tint', -.25)
    before = owner.snapshot(); state = C.capture(engine); C.install(state, recipe(texture, clarity))
    REPLAY.replay_preset(engine, state, mode='preset')
    after = owner.snapshot()
    for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
        assert after[key] == before[key]
    assert all(row in after['overrides'] for row in before['overrides'])
    added = [row for row in after['overrides'] if row not in before['overrides']]
    expected = {('/' + key, value) for key, value in (('texture', texture), ('clarity', clarity)) if value != 0.}
    assert {(leaf['parameter_path'], leaf['value']) for leaf in added} == expected
    assert all(leaf['scope'] == 'face' and leaf['target_id'] == FACE and leaf['operation_id'] == C.OP for leaf in added)
    assert len(calls) == len(owner.commits) == 1 and calls[0][1]['strict_local'] is True
    assert engine._people_analyses[ASSET][FACE] is analysis


@pytest.mark.parametrize('fault', ['native', 'analysis', 'target', 'unmanaged', 'source'])
def test_replay_rechecks_live_evidence_and_source_not_capture_flags(monkeypatch, fault):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(.3))
    if fault == 'native': monkeypatch.setattr(N, 'available', lambda: False)
    elif fault == 'analysis': analysis['excluded'] = None
    elif fault == 'target': engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    elif fault == 'unmanaged': engine._people_managed = lambda: False
    else: engine._people_source = lambda: {'sha256': 'e' * 64, 'width': 640, 'height': 480}
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert not owner.commits and not calls


@pytest.mark.parametrize('path,value', [('/texture', -.25), ('/clarity', .25)])
def test_unchanged_active_texture_or_clarity_still_requires_strict_actual_renderer(monkeypatch, path, value):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, path, value)
    REPLAY.replay_preset(engine, C.capture(engine))
    assert not owner.commits and calls[-1][1]['strict_local'] is True


def test_failed_texture_render_rolls_back_exact_canonical_graph(monkeypatch):
    engine, owner, _, _, _ = replay_fixture(monkeypatch, fail=True)
    before = owner.snapshot(); state = C.capture(engine); C.install(state, recipe(-.2, .3))
    with pytest.raises(RuntimeError, match='target-render refusal'): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and len(owner.commits) == 2


def test_generic_preset_never_guesses_among_multiple_enabled_faces(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    neighbour, _ = graph(face_id='neighbour-face')
    owner.value['faces']['neighbour-face'] = neighbour['faces']['neighbour-face']
    before = owner.snapshot(); state = C.capture(engine); C.install(state, recipe(.2))
    with pytest.raises(ValueError, match='one explicit unambiguous enabled face'):
        REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and not owner.commits and not calls


def test_unrelated_legacy_replay_needs_no_texture_target(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    engine._people_targets.clear()
    REPLAY.replay_preset(engine, {})
    assert not owner.commits and len(calls) == 1 and C.FIELD not in calls[0][0]


def test_scalar_batch_selection_cannot_transfer_schema_or_support():
    from lumaretouch_engine import people_batch_transfer as B
    value, _ = graph(); selected = {'source_ref': P.face_ref(value['faces'][FACE]),
        'selection': {C.OP: ['/texture', '/clarity']}, 'target_policy': 'confirmed_person_only'}
    assert B.options(selected, [C.OP], ASSET) == selected
    for path in ('/version', '/face_ref', '/body_ref', '/face_skin', '/excluded', '/landmarks', '/source_detail', '/detail_bands', '/coverage'):
        wrong = deepcopy(selected); wrong['selection'][C.OP] = [path]
        with pytest.raises(ValueError, match='scalar parameter leaves'): B.options(wrong, [C.OP], ASSET)


@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('refused', [False, True])
@pytest.mark.parametrize('target_policy', ['explicit_face_map', 'confirmed_person_only'])
@pytest.mark.parametrize('texture,clarity', [(-.6, 0.), (.6, 0.), (0., .4), (-.6, .4)])
def test_people_transfer_routes_each_effective_target_through_full_renderer(monkeypatch, derived, refused, target_policy, texture, clarity):
    """Mocked full renderer: routing and refusal only, not pixel acceptance."""
    from lumaretouch_engine import people_batch_transfer as B, people_transfer_inventory as I
    from lumaretouch_engine import full_candidate_render as FULL
    source, _ = graph(face_id='source-face'); target, _ = graph('e' * 64)
    if target_policy == 'confirmed_person_only':
        for value, face_id in ((source, 'source-face'), (target, FACE)):
            value['persons']['confirmed-person'] = {'anonymous': True}
            value['links'] = [{'face_instance_id': face_id, 'person_id': 'confirmed-person',
                'state': 'confirmed', 'confirmation_revision': 0}]
    source = P.set_override(source, 'face', 'source-face', C.OP, '/texture', texture)
    source = P.set_override(source, 'face', 'source-face', C.OP, '/clarity', clarity)
    target = P.set_override(target, 'face', FACE, COLOUR.OP, '/tint', -.2)
    states = {'source': source, 'target': target}; owner = Owner(source)
    rows = [{'document_id': identity, 'path': identity + '.jpg', 'state': {}} for identity in states]
    if derived: rows[1]['state']['_creative_base'] = {'fixture': 'target-owned immutable source'}
    def proof(value, identity):
        out = endpoint(value, identity, scope='project' if target_policy == 'confirmed_person_only' else None)
        if derived and identity == 'target':
            out['source_proof']['creative_source'] = {'sha256': 'e' * 64, 'width': 640, 'height': 480}
            out['source_proof']['original_sha256'] = 'f' * 64
        return out
    versions = SimpleNamespace(workspace='workspace', version=lambda row:
        SimpleNamespace(document_id=row['document_id'], revision=2))
    batch = SimpleNamespace(versions=versions,
        documents=SimpleNamespace(rows=lambda: rows, current_index=lambda: 0, remember_current=lambda: None),
        target_indices=lambda _docs: ([1], []))
    engine = SimpleNamespace(_people_bind=lambda: None, _people_owner=lambda: owner,
        _batch_controller=lambda: batch, _document_versions=lambda: versions,
        _body_bank=lambda: pytest.fail('Texture never requests body coverage'))
    monkeypatch.setattr(B.V, 'row_snapshot', lambda _engine, row: deepcopy(states[row['document_id']]))
    monkeypatch.setattr(I, 'proof', lambda _engine, row, value: proof(value, row['document_id']))
    def verify(_engine, row, value, expected):
        assert expected == proof(value, row['document_id']); return expected
    monkeypatch.setattr(I, 'verify', verify)
    monkeypatch.setattr(B.SOURCE, 'row_proof', lambda row: proof(states[row['document_id']], row['document_id'])['source_proof'])
    def verify_source(row, expected):
        assert expected == B.SOURCE.row_proof(row); return expected
    monkeypatch.setattr(B.SOURCE, 'verify_row', verify_source)
    renders = []
    def render(actual_engine, row, state, document_id, revision, *, people_graph):
        assert actual_engine is engine and row is rows[1] and state is rows[1]['state']
        assert (document_id, revision) == ('target', '2')
        for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
            assert people_graph[key] == target[key]
        added = [leaf for leaf in people_graph['overrides'] if leaf not in target['overrides']]
        assert {(leaf['parameter_path'], leaf['value']) for leaf in added} == {
            ('/texture', texture), ('/clarity', clarity)}
        assert all(leaf['scope'] == 'face' and leaf['target_id'] == FACE and leaf['operation_id'] == C.OP for leaf in added)
        assert all(leaf in people_graph['overrides'] for leaf in target['overrides'])
        renders.append(deepcopy(people_graph))
        if refused: raise ValueError('Target-owned texture detail renderer refused; no source-support fallback')
        return None, {'fixture': 'routing only'}
    monkeypatch.setattr(FULL, 'render', render)
    plans = []
    def freeze(workspace, source_id, revision, path, modules, params, policy, targets, rejected):
        plans.append(targets)
        return SimpleNamespace(modules=modules, token='fixture-token', workspace=workspace, expires_ns=1)
    replies = []; controller = SimpleNamespace(store=SimpleNamespace(create=freeze), _source=lambda _plan: {},
        emit=lambda event: None, emit_result=lambda _request, body: replies.append(body))
    request = {'cmd': 'batch', 'action': 'preflight', 'request_id': 'fixture-texture',
        'docs': ['target'], 'module_scope': [C.OP], 'people_transfer': {
            'source_ref': P.face_ref(source['faces']['source-face']), 'selection': {C.OP: ['/texture', '/clarity']},
            'target_policy': 'explicit_face_map', 'source': proof(source, 'source'),
            'targets': [{'target': proof(target, 'target'), 'target_refs': [P.face_ref(target['faces'][FACE])]}]}}
    if target_policy == 'confirmed_person_only':
        request['people_transfer'] = {key: value for key, value in request['people_transfer'].items()
            if key not in ('source', 'targets')}
        request['people_transfer']['target_policy'] = target_policy
    before = deepcopy(states); B.preflight(engine, controller, request)
    assert states == before and not owner.commits and len(renders) == 1
    result = replies[-1]; payload = result['targets'][0]['people_transfer']
    assert (result['ok'], result['blocked']) == ((0, 1) if refused else (1, 0))
    if refused:
        assert payload is None and plans[0][0].people_json is None
        assert 'Target-owned texture detail renderer refused' in result['targets'][0]['blocked']
    else:
        assert payload['parameters'] == [
            {'operation_id': C.OP, 'parameter_path': '/clarity', 'value': clarity},
            {'operation_id': C.OP, 'parameter_path': '/texture', 'value': texture}]
        assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
        assert not any('coverage' in key or 'support' in key for key in payload)
        assert json.loads(plans[0][0].people_json) == payload


def test_confirmed_people_transfer_keeps_scalar_only_same_owner_contract():
    from lumaretouch_engine.people_confirmed_transfer import prepare_confirmed
    from lumaretouch_engine import people_transfer_adapter as T
    source, _ = graph(face_id='source-face'); target, _ = graph('e' * 64)
    for value, face_id in ((source, 'source-face'), (target, FACE)):
        value['persons']['confirmed-person'] = {'anonymous': True}
        value['links'] = [{'face_instance_id': face_id, 'person_id': 'confirmed-person',
            'state': 'confirmed', 'confirmation_revision': 0}]
    source = P.set_override(source, 'face', 'source-face', C.OP, '/texture', -.4)
    source = P.set_override(source, 'face', 'source-face', C.OP, '/clarity', .8)
    target = P.set_override(target, 'face', FACE, C.OP, '/clarity', .2)
    source_owner = endpoint(source, 'source', scope='project')
    target_owner = endpoint(target, 'target', scope='project')
    kwargs = {'source_document': source_owner['document'], 'target_document': target_owner['document'],
        'source_owner': source_owner, 'target_owner': target_owner}
    payload = prepare_confirmed(source, target, P.face_ref(source['faces']['source-face']), 'e' * 64,
        {C.OP: ['/texture']}, A.defaults(), **kwargs)
    candidate = T.candidate(payload, source, target, **kwargs)
    assert payload['target_policy'] == 'confirmed_person_only'
    assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': '/texture', 'value': -.4}]
    assert candidate['faces'] == target['faces'] and candidate['links'] == target['links']
    assert next(leaf['value'] for leaf in candidate['overrides']
        if leaf['operation_id'] == C.OP and leaf['parameter_path'] == '/clarity') == .2
    changed_owner = deepcopy(target_owner)
    changed_owner['source_proof'] = {'asset_sha256': 'f' * 64,
        'creative_source': None, 'original_sha256': 'f' * 64}
    with pytest.raises(ValueError, match='owner, source or graph changed'):
        T.verify(payload, source, target, **{**kwargs, 'target_owner': changed_owner})


def test_selected_clarity_transfer_preserves_target_texture():
    from lumaretouch_engine import people_transfer_adapter as T
    source, _ = graph(face_id='source-face'); target, _ = graph('e' * 64)
    source = P.set_override(source, 'face', 'source-face', C.OP, '/texture', .7)
    source = P.set_override(source, 'face', 'source-face', C.OP, '/clarity', .4)
    target = P.set_override(target, 'face', FACE, C.OP, '/texture', -.3)
    source_owner = endpoint(source, 'source'); target_owner = endpoint(target, 'target')
    kwargs = {'source_document': source_owner['document'], 'target_document': target_owner['document'],
        'source_owner': source_owner, 'target_owner': target_owner}
    payload = T.prepare(source, target, P.face_ref(source['faces']['source-face']),
        [P.face_ref(target['faces'][FACE])], {C.OP: ['/clarity']}, A.defaults(), **kwargs)
    payload['target_policy'] = 'explicit_face_map'
    candidate = T.candidate(payload, source, target, **kwargs)
    assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': '/clarity', 'value': .4}]
    assert {leaf['parameter_path']: leaf['value'] for leaf in candidate['overrides']
        if leaf['operation_id'] == C.OP} == {'/texture': -.3, '/clarity': .4}
    assert candidate['faces'] == target['faces'] and candidate['groups'] == target['groups']
