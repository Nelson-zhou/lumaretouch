"""AUTHORED / UNRUN: independent finish scalars and canonical preset replay.

Reuses the existing synthetic face fixture; native readiness and rendering are
mocked. These are not runtime, real-inference, pixel-quality or acceptance results.
No product imports, collection, execution, build or typecheck ran while authoring.
"""
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
from lumaretouch_engine import skin_finish_scope as C, skin_finish_state as S
from lumaretouch_engine import skin_finish_native as N, skin_colour_scope as COLOUR
from lumaretouch_engine import people_state as P, people_algorithms as A, people_scope as REPLAY, scope as SC
from lumaretouch_engine.workflow_ports import WorkflowPortsMixin
from test_skin_colour_scope_unrun import (ASSET, FACE, Owner, graph, endpoint,
    engine_fixture as colour_engine_fixture, replay_fixture as colour_replay_fixture,
    isolate_other_captures)


def recipe(whitening=0., rosiness=0.):
    return {'recipe': {'version': 1, 'whitening': whitening, 'rosiness': rosiness}}


def engine_fixture(monkeypatch):
    value = colour_engine_fixture(monkeypatch)
    monkeypatch.setattr(N, 'available', lambda: True)
    return value


def replay_fixture(monkeypatch, *, fail=False):
    value = colour_replay_fixture(monkeypatch, fail=fail)
    monkeypatch.setattr(N, 'available', lambda: True)
    return value


def test_distinct_unsigned_registration_does_not_reinterpret_signed_colour():
    assert C.OP == 'lnx.skin_finish.v1' and C.OP != COLOUR.OP
    assert SC.MODULES[C.OP]['read'] is C.params_of
    assert SC.MODULES[C.OP]['write'] is C.install
    assert SC.MODULES[C.OP]['single_face'] is True
    assert SC.MODULES[C.OP]['state_fields'] == (C.FIELD,)
    assert C.OP not in SC.DERIVED_PARAMETER_OPS
    assert A.defaults()[C.OP] == {'/whitening': 0., '/rosiness': 0.}
    assert A.defaults()[COLOUR.OP] == {'/temperature': 0., '/tint': 0.}
    assert SC.check_params(C.OP, recipe(1, .25)) == recipe(1., .25)
    assert SC.check_params(COLOUR.OP, {'recipe': {'version': 1, 'temperature': -.6, 'tint': .8}}) == {
        'recipe': {'version': 1, 'temperature': -.6, 'tint': .8}}
    with pytest.raises(SC.ScopeError): SC.check_params(C.OP, COLOUR.params_of({
        COLOUR.FIELD: COLOUR.S.neutral(), COLOUR.TARGET: {'asset_sha256': ASSET, 'face_instance_id': FACE, 'analysis_revision': 0}}))


@pytest.mark.parametrize('value', [True, False, None, '0.5', float('nan'), float('inf'), -.01, 1.01, 10**1000])
@pytest.mark.parametrize('key', ['whitening', 'rosiness'])
def test_invalid_finish_scalar_does_not_mutate_capture(monkeypatch, key, value):
    engine, _, _, _ = engine_fixture(monkeypatch); state = C.capture(engine); before = deepcopy(state)
    params = recipe(); params['recipe'][key] = value
    with pytest.raises(ValueError): C.install(state, params)
    assert state == before


@pytest.mark.parametrize('key', ['face_ref', 'body_ref', 'mask', 'body_skin', 'coverage',
    'skin_colour_body_visibility', 'skin_finish_body_visibility', 'temperature', 'tint'])
def test_portable_finish_rejects_evidence_and_signed_colour_fields(key):
    with pytest.raises(ValueError): C.check_params({**recipe(.3), key: {}})
    params = recipe(.3); params['recipe'][key] = {}
    with pytest.raises(ValueError): C.check_params(params)
    with pytest.raises(ValueError): C.check_params({'recipe': None})


def test_workflow_capture_exports_only_finish_scalars_and_keeps_colour(monkeypatch):
    engine, owner, analysis, current = engine_fixture(monkeypatch); isolate_other_captures(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/whitening', .35)
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/rosiness', .4)
    owner.value = P.set_override(owner.value, 'face', FACE, COLOUR.OP, '/temperature', -.6)
    captured = WorkflowPortsMixin._people_preset_capture(engine)
    portable = SC.params_of(captured, [C.OP, COLOUR.OP])
    assert portable[C.OP] == recipe(.35, .4)
    assert portable[COLOUR.OP] == {'recipe': {'version': 1, 'temperature': -.6, 'tint': 0.}}
    assert captured[C.TARGET] == P.face_ref(owner.value['faces'][FACE])
    assert captured['_skin_finish_supported'] is True and captured[C.REQUESTED] is False
    assert json.loads(json.dumps(portable[C.OP])) == recipe(.35, .4)
    assert 'face_skin' not in captured and current == {}
    assert engine._people_analyses[ASSET][FACE] is analysis


@pytest.mark.parametrize('fault', ['merged-skin', 'observation', 'excluded', 'ref', 'model',
    'landmarks', 'synthetic', 'dimensions'])
def test_capture_demands_own_real_face_analysis(monkeypatch, fault):
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
    else: engine._people_source = lambda: {'sha256': ASSET, 'width': 641, 'height': 480}
    state = C.capture(engine)
    assert state['_skin_finish_supported'] is False
    with pytest.raises(ValueError): C.install(state, recipe(.2))
    assert not owner.commits


def test_native_unavailable_refuses_active_but_allows_exact_target_neutral(monkeypatch):
    engine, _, analysis, _ = engine_fixture(monkeypatch)
    monkeypatch.setattr(N, 'available', lambda: False)
    state = C.capture(engine)
    with pytest.raises(ValueError, match='Rust'): C.install(state, recipe(.2))
    analysis['excluded'] = None
    state = C.capture(engine); C.install(state, recipe())
    assert state[C.FIELD] == S.neutral() and state[C.REQUESTED] is True


@pytest.mark.parametrize('fault', ['cursor', 'group', 'stale', 'disabled', 'unmanaged'])
def test_capture_needs_explicit_current_enabled_face(monkeypatch, fault):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    if fault == 'cursor': engine._people_cursors.clear()
    elif fault == 'group': engine._people_targets[ASSET] = {'scope': 'group', 'target_id': 'preserved'}
    elif fault == 'stale': engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    elif fault == 'disabled': owner.value['faces'][FACE]['enabled'] = False
    else: engine._people_managed = lambda: False
    state = C.capture(engine)
    assert state[C.TARGET] is None
    with pytest.raises(ValueError): C.params_of(state)
    with pytest.raises(ValueError): C.install(state, recipe())


def test_install_changes_only_scalar_transport_and_keeps_generic_derived_guard(monkeypatch):
    engine, _, _, _ = engine_fixture(monkeypatch)
    before = C.capture(engine); after = SC.apply_modules(before, {C.OP: recipe(.3, .5)})
    assert {key for key in after if before.get(key) != after[key]} == {C.FIELD, C.REQUESTED}
    assert after[C.TARGET] == before[C.TARGET]
    with pytest.raises(ValueError, match='合成来源'): C.install({**before, '_creative_base': {}}, recipe(.3))
    with pytest.raises(SC.ScopeError): SC.check_derived_modules({C.OP: recipe()})
    with pytest.raises(ValueError): SC.apply_modules({}, {C.OP: recipe(.3)})


def test_replay_consumes_only_changed_finish_leaves_in_existing_owner(monkeypatch):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, COLOUR.OP, '/tint', -.25)
    before = owner.snapshot(); state = C.capture(engine); C.install(state, recipe(.3, .45))
    REPLAY.replay_preset(engine, state, mode='preset')
    after = owner.snapshot()
    for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
        assert after[key] == before[key]
    assert all(row in after['overrides'] for row in before['overrides'])
    added = [row for row in after['overrides'] if row not in before['overrides']]
    assert {(row['operation_id'], row['parameter_path'], row['value']) for row in added} == {
        (C.OP, '/whitening', .3), (C.OP, '/rosiness', .45)}
    assert all(row['scope'] == 'face' and row['target_id'] == FACE for row in added)
    assert len(calls) == len(owner.commits) == 1 and calls[0][1]['strict_local'] is True
    assert engine._people_analyses[ASSET][FACE] is analysis


@pytest.mark.parametrize('fault', ['native', 'analysis', 'target', 'unmanaged'])
def test_replay_rechecks_live_admission_not_captured_true_flags(monkeypatch, fault):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(.3))
    if fault == 'native': monkeypatch.setattr(N, 'available', lambda: False)
    elif fault == 'analysis': analysis['excluded'] = None
    elif fault == 'target': engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    else: engine._people_managed = lambda: False
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert not owner.commits and not calls


def test_unchanged_active_finish_still_requests_strict_actual_renderer(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/rosiness', .25)
    REPLAY.replay_preset(engine, C.capture(engine))
    assert not owner.commits and calls[-1][1]['strict_local'] is True


def test_failed_finish_render_rolls_back_exact_canonical_graph(monkeypatch):
    engine, owner, _, _, _ = replay_fixture(monkeypatch, fail=True)
    before = owner.snapshot(); state = C.capture(engine); C.install(state, recipe(.2, .2))
    with pytest.raises(RuntimeError, match='target-render refusal'): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and len(owner.commits) == 2


def test_scalar_batch_selection_does_not_allow_version_or_support_transport():
    from lumaretouch_engine import people_batch_transfer as B
    value, _ = graph(); selected = {'source_ref': P.face_ref(value['faces'][FACE]),
        'selection': {C.OP: ['/whitening', '/rosiness']}, 'target_policy': 'confirmed_person_only'}
    assert B.options(selected, [C.OP], ASSET) == selected
    for path in ('/temperature', '/tint', '/version', '/face_ref', '/body_ref', '/mask', '/coverage'):
        wrong = deepcopy(selected); wrong['selection'][C.OP] = [path]
        with pytest.raises(ValueError, match='scalar parameter leaves'): B.options(wrong, [C.OP], ASSET)


@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.parametrize('refused', [False, True])
def test_full_target_renderer_routes_original_and_derived_scalar_review(monkeypatch, derived, refused):
    """Mocked full renderer: owner routing only, not pixels or native acceptance."""
    from lumaretouch_engine import people_batch_transfer as B, people_transfer_inventory as I
    from lumaretouch_engine import full_candidate_render as FULL
    source, _ = graph(face_id='source-face'); target, _ = graph('e' * 64)
    source = P.set_override(source, 'face', 'source-face', C.OP, '/whitening', .6)
    target = P.set_override(target, 'face', FACE, C.OP, '/rosiness', .2)
    states = {'source': source, 'target': target}; owner = Owner(source)
    rows = [{'document_id': identity, 'path': identity + '.jpg', 'state': {}} for identity in states]
    if derived: rows[1]['state']['_creative_base'] = {'fixture': 'target-owned immutable source'}
    def proof(value, identity):
        out = endpoint(value, identity)
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
        _batch_controller=lambda: batch, _document_versions=lambda: versions)
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
        assert people_graph['faces'] == target['faces'] and people_graph['groups'] == target['groups']
        added = [leaf for leaf in people_graph['overrides'] if leaf not in target['overrides']]
        assert added == [{'scope': 'face', 'target_id': FACE, 'operation_id': C.OP,
            'parameter_path': '/whitening', 'value': .6}]
        assert next(leaf['value'] for leaf in people_graph['overrides']
            if leaf['operation_id'] == C.OP and leaf['parameter_path'] == '/rosiness') == .2
        renders.append(deepcopy(people_graph))
        if refused: raise ValueError('Target-owned finish renderer refused; no source-support fallback')
        return None, {'fixture': 'routing only'}
    monkeypatch.setattr(FULL, 'render', render)
    plans = []
    def freeze(workspace, source_id, revision, path, modules, params, policy, targets, rejected):
        plans.append(targets)
        return SimpleNamespace(modules=modules, token='fixture-token', workspace=workspace, expires_ns=1)
    replies = []; controller = SimpleNamespace(store=SimpleNamespace(create=freeze), _source=lambda _plan: {},
        emit=lambda event: None, emit_result=lambda _request, body: replies.append(body))
    request = {'cmd': 'batch', 'action': 'preflight', 'request_id': 'fixture-finish',
        'docs': ['target'], 'module_scope': [C.OP], 'people_transfer': {
            'source_ref': P.face_ref(source['faces']['source-face']), 'selection': {C.OP: ['/whitening']},
            'target_policy': 'explicit_face_map', 'source': proof(source, 'source'),
            'targets': [{'target': proof(target, 'target'), 'target_refs': [P.face_ref(target['faces'][FACE])]}]}}
    before = deepcopy(states); B.preflight(engine, controller, request)
    assert states == before and not owner.commits and len(renders) == 1
    result = replies[-1]; payload = result['targets'][0]['people_transfer']
    assert (result['ok'], result['blocked']) == ((0, 1) if refused else (1, 0))
    if refused:
        assert payload is None and plans[0][0].people_json is None
        assert 'Target-owned finish renderer refused' in result['targets'][0]['blocked']
    else:
        assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': '/whitening', 'value': .6}]
        assert payload['skin_finish_coverage'] == {'version': 1, 'support_transfer': 'none', 'targets': [
            {'face_ref': P.face_ref(target['faces'][FACE]), 'scope': 'face-only', 'body_review_sha256': None}]}
        assert 'skin_colour_coverage' not in payload
        assert json.loads(plans[0][0].people_json) == payload
