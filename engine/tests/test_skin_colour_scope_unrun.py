"""AUTHORED / UNRUN: scalar preset and existing canonical replay contracts.

Synthetic evidence and monkeypatched native availability are schema fixtures,
not real inference, Rust execution, photographic quality or acceptance claims.
No product imports, fixture execution or test collection ran during authoring.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import numpy as np
import pytest

from lumaretouch_engine import skin_colour_scope as C, skin_colour_state as S
from lumaretouch_engine import people_state as P, people_algorithms as A
from lumaretouch_engine import people_scope as REPLAY, scope as SC
from lumaretouch_engine import skin_colour_native as N, skin_colour_support as SUPPORT
from lumaretouch_engine.workflow_ports import WorkflowPortsMixin

ASSET = 'a' * 64
FACE = 'target-face'


def recipe(temperature=0., tint=0.):
    return {'recipe': {'version': 1, 'temperature': temperature, 'tint': tint}}


def graph(asset=ASSET, face_id=FACE):
    landmarks = np.full((478, 3), .5, dtype='<f4')
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b' * 64,
        'semantic_model_sha256': 'c' * 64,
        'landmark_digest': sha256(landmarks.tobytes()).hexdigest(), 'status': 'verified',
        'source_width': 640, 'source_height': 480, 'orientation': 'exif_normalized_once'}
    value = P.empty(); face = P.new_face(asset, [.1, .2, .6, .8], evidence)
    face['face_instance_id'] = face_id; value['faces'][face_id] = face
    face['local_assets']['target-only'] = {'owner': P.face_ref(face), 'content_sha256': 'd' * 64, 'kind': 'fixture'}
    value['groups']['preserved'] = {'label': 'Target group', 'priority': 1, 'face_ids': [face_id]}
    value = P.set_override(value, 'group', 'preserved', A.ENHANCE, '/sclera', .2)
    return value, {'face_ref': P.face_ref(face), 'evidence': deepcopy(evidence),
        'landmarks': landmarks, 'skin': np.ones((8, 10), np.float32),
        'excluded': np.zeros((8, 10), np.float32), 'face_skin': np.ones((8, 10), np.float32),
        'face_skin_observation': {'contract': SUPPORT.CONTRACT, 'source_sha256': asset,
            'semantic_model_sha256': 'c' * 64, 'producer_width': 10, 'producer_height': 8}}


class Owner:
    def __init__(self, value):
        self.value = P.check(value); self.fence = 0
        self.association_fence = value['association_revision']; self.commits = []

    def snapshot(self): return deepcopy(self.value)

    def commit(self, value, *, expected_fence):
        assert expected_fence == self.fence
        self.value = P.check(value); self.fence += 1; self.commits.append(self.snapshot())


def engine_fixture(monkeypatch):
    value, analysis = graph(); owner = Owner(value); current = {}
    ref = P.face_ref(value['faces'][FACE])
    engine = SimpleNamespace(_people_managed=lambda: True, _people_owner=lambda: owner,
        _people_source=lambda: {'sha256': ASSET, 'width': 640, 'height': 480},
        _people_cursors={ASSET: FACE},
        _people_targets={ASSET: {'scope': 'face', 'target_id': FACE, 'face_ref': ref}},
        _people_analyses={ASSET: {FACE: analysis}}, _people_analysis_key='old',
        _capture_state=lambda: deepcopy(current))
    monkeypatch.setattr(N, 'available', lambda: True)
    return engine, owner, analysis, current


def isolate_other_captures(monkeypatch):
    from lumaretouch_engine import eye_light_scope, blush_makeup_scope, lipstick_scope, eyeliner_scope
    from lumaretouch_engine import eyelash_scope, brow_makeup_scope, iris_makeup_scope
    monkeypatch.setattr(eye_light_scope, 'capture', lambda engine: engine._capture_state())
    for module in (blush_makeup_scope, lipstick_scope, eyeliner_scope, eyelash_scope, brow_makeup_scope, iris_makeup_scope):
        monkeypatch.setattr(module, 'capture', lambda engine, base: base)


def replay_fixture(monkeypatch, *, fail=False):
    engine, owner, analysis, current = engine_fixture(monkeypatch)
    isolate_other_captures(monkeypatch); calls = []
    def replay(state, **kwargs):
        calls.append((deepcopy(state), kwargs))
        if fail: raise RuntimeError('authored target-render refusal')
        return {'event': 'frame', 'render_ms': 0}
    engine._replay_state = replay
    return engine, owner, analysis, current, calls


def test_registration_is_scalar_only_and_generic_derived_is_not_claimed():
    assert C.OP == 'lnx.skin_colour.v1'
    assert SC.MODULES[C.OP]['read'] is C.params_of
    assert SC.MODULES[C.OP]['write'] is C.install
    assert SC.MODULES[C.OP]['single_face'] is True
    assert SC.MODULES[C.OP]['state_fields'] == (C.FIELD,)
    assert C.OP not in SC.DERIVED_PARAMETER_OPS
    assert A.defaults()[C.OP] == {'/temperature': 0., '/tint': 0.}
    assert SC.check_params(C.OP, recipe(-1, 1)) == recipe(-1., 1.)


@pytest.mark.parametrize('value', [True, False, None, '0.5', float('nan'), float('inf'), -1.01, 1.01, 10**1000])
@pytest.mark.parametrize('key', ['temperature', 'tint'])
def test_invalid_scalar_refuses_without_mutating_context(monkeypatch, key, value):
    engine, _, _, _ = engine_fixture(monkeypatch); state = C.capture(engine); before = deepcopy(state)
    params = recipe(); params['recipe'][key] = value
    with pytest.raises(ValueError): C.install(state, params)
    assert state == before


@pytest.mark.parametrize('key,value', [('face_ref', {}), ('mask', []), ('face_skin', []),
    ('supported', True), ('enabled', True), ('whole_body', True)])
def test_portable_recipe_rejects_source_identity_masks_and_support_claims(key, value):
    with pytest.raises(ValueError): C.check_params({**recipe(.2), key: value})
    params = recipe(.2); params['recipe'][key] = value
    with pytest.raises(ValueError): C.check_params(params)
    with pytest.raises(ValueError): C.check_params({'recipe': None})


def test_actual_workflow_capture_exports_values_not_source_evidence(monkeypatch):
    engine, owner, analysis, current = engine_fixture(monkeypatch); isolate_other_captures(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/temperature', -.35)
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/tint', .4)
    captured = WorkflowPortsMixin._people_preset_capture(engine)
    assert C.params_of(captured) == recipe(-.35, .4)
    assert captured[C.TARGET] == P.face_ref(owner.value['faces'][FACE])
    assert captured['_skin_colour_supported'] is True and not captured[C.REQUESTED]
    portable = SC.params_of(captured, [C.OP])
    assert json.loads(json.dumps(portable)) == {C.OP: recipe(-.35, .4)}
    assert current == {} and 'face_skin' not in captured
    assert engine._people_analyses[ASSET][FACE] is analysis


@pytest.mark.parametrize('fault', ['merged-skin-only', 'missing-observation', 'missing-excluded',
    'stale-ref', 'wrong-model', 'wrong-landmarks', 'synthetic', 'wrong-source-size'])
def test_capture_requires_actual_matching_target_evidence(monkeypatch, fault):
    engine, owner, analysis, _ = engine_fixture(monkeypatch)
    if fault == 'merged-skin-only': analysis['face_skin'] = analysis['face_skin_observation'] = None
    elif fault == 'missing-observation': analysis.pop('face_skin_observation')
    elif fault == 'missing-excluded': analysis['excluded'] = None
    elif fault == 'stale-ref': analysis['face_ref']['analysis_revision'] += 1
    elif fault == 'wrong-model': analysis['face_skin_observation']['semantic_model_sha256'] = 'e' * 64
    elif fault == 'wrong-landmarks': analysis['landmarks'][0, 0] = .7
    elif fault == 'synthetic':
        owner.value['faces'][FACE]['evidence']['status'] = 'synthetic'
        analysis['evidence']['status'] = 'synthetic'
    elif fault == 'wrong-source-size': engine._people_source = lambda: {'sha256': ASSET, 'width': 641, 'height': 480}
    captured = C.capture(engine)
    assert captured['_skin_colour_supported'] is False
    with pytest.raises(ValueError): C.install(captured, recipe(.2))
    assert not owner.commits


def test_unanalysed_neighbour_retains_box_veto_without_fabricated_support(monkeypatch):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    other = deepcopy(owner.value['faces'][FACE]); other['face_instance_id'] = 'neighbour'
    other['local_assets'] = {}; other['enabled'] = False
    other['evidence']['status'] = 'unresolved'
    owner.value['faces']['neighbour'] = other
    state = C.capture(engine); C.install(state, recipe(.2))
    assert state['_skin_colour_supported'] is True
    assert set(engine._people_analyses[ASSET]) == {FACE}
    assert owner.value['faces']['neighbour'] == other


@pytest.mark.parametrize('fault', ['no-cursor', 'group-target', 'stale-target', 'disabled', 'unmanaged'])
def test_cursor_alone_never_authorizes_a_skin_preset(monkeypatch, fault):
    engine, owner, _, _ = engine_fixture(monkeypatch)
    if fault == 'no-cursor': engine._people_cursors.clear()
    elif fault == 'group-target': engine._people_targets[ASSET] = {'scope': 'group', 'target_id': 'preserved'}
    elif fault == 'stale-target': engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    elif fault == 'disabled': owner.value['faces'][FACE]['enabled'] = False
    else: engine._people_managed = lambda: False
    captured = C.capture(engine)
    assert captured[C.TARGET] is None
    with pytest.raises(ValueError): C.params_of(captured)
    with pytest.raises(ValueError): C.install(captured, recipe())


def test_unavailable_native_blocks_active_but_neutral_can_clear_an_explicit_face(monkeypatch):
    engine, _, analysis, _ = engine_fixture(monkeypatch)
    monkeypatch.setattr(N, 'available', lambda: False)
    captured = C.capture(engine)
    with pytest.raises(ValueError, match='Rust'): C.install(captured, recipe(-.2, .3))
    analysis['excluded'] = None
    captured = C.capture(engine); C.install(captured, recipe())
    assert captured[C.FIELD] == S.neutral() and captured[C.REQUESTED] is True


def test_generic_unmanaged_batch_context_explicitly_refuses_not_neutral_success():
    with pytest.raises(ValueError, match='人物参数映射'): SC.params_of({}, [C.OP])
    with pytest.raises(ValueError, match='人物参数映射'): SC.apply_modules({}, {C.OP: recipe(.4)})


def test_install_changes_only_scalar_transport_and_derived_route_refuses(monkeypatch):
    engine, _, _, _ = engine_fixture(monkeypatch)
    before = C.capture(engine); after = SC.apply_modules(before, {C.OP: recipe(-.3, .5)})
    assert before[C.FIELD] == S.neutral()
    assert {key for key in after if before.get(key) != after[key]} == {C.FIELD, C.REQUESTED}
    assert after[C.TARGET] == before[C.TARGET]
    with pytest.raises(ValueError, match='合成来源'):
        C.install({**before, '_creative_base': {'not': 'an original source'}}, recipe(.3))
    with pytest.raises(SC.ScopeError): SC.check_derived_modules({C.OP: recipe()})


def test_replay_consumes_scalar_transport_into_existing_canonical_owner(monkeypatch):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    before = owner.snapshot(); state = C.capture(engine)
    C.install(state, recipe(-.3, .45)); REPLAY.replay_preset(engine, state, mode='preset', replayed_for='fixture')
    after = owner.snapshot()
    for key in ('faces', 'persons', 'groups', 'links', 'analysis_runs', 'unresolved_legacy'):
        assert after[key] == before[key]
    assert all(row in after['overrides'] for row in before['overrides'])
    added = [row for row in after['overrides'] if row not in before['overrides']]
    assert {(row['operation_id'], row['parameter_path'], row['value']) for row in added} == {
        (C.OP, '/temperature', -.3), (C.OP, '/tint', .45)}
    assert all(row['scope'] == 'face' and row['target_id'] == FACE for row in added)
    assert len(calls) == len(owner.commits) == 1 and calls[0][1]['strict_local'] is True
    assert engine._people_analyses[ASSET][FACE] is analysis


@pytest.mark.parametrize('fault', ['native', 'analysis', 'target', 'unmanaged'])
def test_replay_rechecks_current_evidence_not_captured_true_flags(monkeypatch, fault):
    engine, owner, analysis, _, calls = replay_fixture(monkeypatch)
    state = C.capture(engine); C.install(state, recipe(.3))
    if fault == 'native': monkeypatch.setattr(N, 'available', lambda: False)
    elif fault == 'analysis': analysis['excluded'] = None
    elif fault == 'target': engine._people_targets[ASSET]['face_ref']['analysis_revision'] += 1
    else: engine._people_managed = lambda: False
    with pytest.raises(ValueError): REPLAY.replay_preset(engine, state)
    assert not owner.commits and not calls


def test_unchanged_active_recipe_still_demands_strict_render(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    owner.value = P.set_override(owner.value, 'face', FACE, C.OP, '/tint', -.25)
    REPLAY.replay_preset(engine, C.capture(engine))
    assert not owner.commits and calls[-1][1]['strict_local'] is True


def test_failed_canonical_replay_rolls_back_exact_prior_graph(monkeypatch):
    engine, owner, _, _, _ = replay_fixture(monkeypatch, fail=True)
    before = owner.snapshot(); state = C.capture(engine); C.install(state, recipe(.2, -.2))
    with pytest.raises(RuntimeError, match='target-render refusal'): REPLAY.replay_preset(engine, state)
    assert owner.snapshot() == before and len(owner.commits) == 2


def test_legacy_unrelated_capture_does_not_create_skin_state_or_require_target(monkeypatch):
    engine, owner, _, _, calls = replay_fixture(monkeypatch)
    engine._people_targets.clear()
    REPLAY.replay_preset(engine, {})
    assert not owner.commits and len(calls) == 1
    assert C.FIELD not in calls[0][0]


def test_confirmed_batch_selection_contains_only_registered_signed_leaves():
    from lumaretouch_engine import people_batch_transfer as B
    value, _ = graph()
    selected = {'source_ref': P.face_ref(value['faces'][FACE]),
        'selection': {C.OP: ['/temperature', '/tint']}, 'target_policy': 'confirmed_person_only'}
    assert B.options(selected, [C.OP], ASSET) == selected
    for forbidden in ('/version', '/face_ref', '/face_skin', '/excluded', '/whole_body'):
        wrong = deepcopy(selected); wrong['selection'][C.OP] = [forbidden]
        with pytest.raises(ValueError, match='scalar parameter leaves'): B.options(wrong, [C.OP], ASSET)


def endpoint(value, identity, *, scope=None):
    from lumaretouch_engine import people_transfer_inventory as I
    face = next(iter(value['faces'].values())); asset = face['asset_sha256']
    return I.check_proof({'document': {'document_id': identity, 'epoch': 'workspace', 'revision': 2},
        'people_scope': identity if scope is None else scope,
        'state_revision': value['revision'], 'association_revision': value['association_revision'],
        'graph_sha256': I.graph_digest(value), 'source_proof': {'asset_sha256': asset,
            'creative_source': None, 'original_sha256': asset}})


@pytest.mark.parametrize('refused', [False, True])
def test_reviewed_face_batch_preflight_routes_scalar_candidate_to_target_full_renderer(monkeypatch, refused):
    """Mock pixels only; exercise the actual preflight/adapter/validate routing."""
    from lumaretouch_engine import people_batch_transfer as B, people_transfer_inventory as I
    from lumaretouch_engine import full_candidate_render as FULL
    source, _ = graph(face_id='source-face'); target, _ = graph('e' * 64)
    source = P.set_override(source, 'face', 'source-face', C.OP, '/temperature', -.6)
    source = P.set_override(source, 'face', 'source-face', C.OP, '/tint', .4)
    target = P.set_override(target, 'face', FACE, C.OP, '/tint', -.2)
    target['faces'][FACE]['local_assets']['target-only']['content_sha256'] = 'f' * 64
    states = {'source': source, 'target': target}; owner = Owner(source)
    rows = [{'document_id': identity, 'path': identity + '.jpg', 'state': {}} for identity in states]
    versions = SimpleNamespace(workspace='workspace', version=lambda row:
        SimpleNamespace(document_id=row['document_id'], revision=2))
    batch = SimpleNamespace(versions=versions,
        documents=SimpleNamespace(rows=lambda: rows, current_index=lambda: 0, remember_current=lambda: None),
        target_indices=lambda _docs: ([1], []))
    engine = SimpleNamespace(_people_bind=lambda: None, _people_owner=lambda: owner,
        _batch_controller=lambda: batch, _document_versions=lambda: versions)
    monkeypatch.setattr(B.V, 'row_snapshot', lambda _engine, row: deepcopy(states[row['document_id']]))
    monkeypatch.setattr(I, 'proof', lambda _engine, row, value: endpoint(value, row['document_id']))
    def verify(_engine, row, value, expected):
        assert expected == endpoint(value, row['document_id'])
        return expected
    monkeypatch.setattr(I, 'verify', verify)
    monkeypatch.setattr(B.SOURCE, 'row_proof', lambda row: endpoint(states[row['document_id']], row['document_id'])['source_proof'])
    def verify_source(row, expected):
        assert expected == B.SOURCE.row_proof(row)
        return expected
    monkeypatch.setattr(B.SOURCE, 'verify_row', verify_source)
    renders = []
    def render(actual_engine, row, state, document_id, revision, *, people_graph):
        assert actual_engine is engine and row is rows[1] and state is rows[1]['state']
        assert (document_id, revision) == ('target', '2')
        assert people_graph['faces'] == target['faces'] and people_graph['groups'] == target['groups']
        added = [leaf for leaf in people_graph['overrides'] if leaf not in target['overrides']]
        assert added == [{'scope': 'face', 'target_id': FACE, 'operation_id': C.OP,
                          'parameter_path': '/temperature', 'value': -.6}]
        assert next(leaf['value'] for leaf in people_graph['overrides']
                    if leaf['operation_id'] == C.OP and leaf['parameter_path'] == '/tint') == -.2
        renders.append(deepcopy(people_graph))
        if refused: raise ValueError('Target own face_skin/native renderer refused; no source mask fallback')
        return None, {'fixture': 'routing only, not rendered pixels'}
    monkeypatch.setattr(FULL, 'render', render)
    plans = []
    def freeze(workspace, source_id, revision, path, modules, params, policy, targets, rejected):
        plans.append(targets)
        return SimpleNamespace(modules=modules, token='fixture-token', workspace=workspace, expires_ns=1)
    events = []; replies = []
    controller = SimpleNamespace(store=SimpleNamespace(create=freeze), _source=lambda _plan: {},
        emit=events.append, emit_result=lambda _request, body: replies.append(body))
    source_owner, target_owner = endpoint(source, 'source'), endpoint(target, 'target')
    request = {'cmd': 'batch', 'action': 'preflight', 'request_id': 'fixture-preflight',
        'docs': ['target'], 'module_scope': [C.OP], 'people_transfer': {
            'source_ref': P.face_ref(source['faces']['source-face']),
            'selection': {C.OP: ['/temperature']}, 'target_policy': 'explicit_face_map',
            'source': source_owner, 'targets': [{'target': target_owner,
                'target_refs': [P.face_ref(target['faces'][FACE])]}]}}
    before = deepcopy(states); B.preflight(engine, controller, request)
    assert states == before and not owner.commits and len(renders) == 1
    result = replies[-1]
    assert (result['ok'], result['blocked']) == ((0, 1) if refused else (1, 0))
    payload = result['targets'][0]['people_transfer']
    if refused:
        assert payload is None and plans[0][0].people_json is None
        assert 'Target own face_skin' in result['targets'][0]['blocked']
    else:
        assert payload['target_refs'] == [P.face_ref(target['faces'][FACE])]
        assert payload['source_ref'] == P.face_ref(source['faces']['source-face'])
        assert payload['parameters'] == [{'operation_id': C.OP, 'parameter_path': '/temperature', 'value': -.6}]
        assert payload['excluded'] == ['local_assets', 'landmarks', 'masks', 'identity_links']
        assert json.loads(plans[0][0].people_json)['parameters'] == payload['parameters']
