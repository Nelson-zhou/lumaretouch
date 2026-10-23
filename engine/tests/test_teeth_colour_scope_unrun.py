"""AUTHORED / UNRUN: tooth scalar scope and canonical preset replay fixtures.

These synthetic schema cases are not rendering or photographic acceptance.
No product imports, test collection or fixture execution occurred in authoring.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import enhance_scope as E, scope as SC
from lumaretouch_engine import people_algorithms as A, people_state as S, people_scope as P
from lumaretouch_engine.ops import enhance as H

ASSET = 'a' * 64
FACE = 'target-face'


def recipe(**amounts):
    return {'recipe': {'version': 1, 'amounts': amounts}}


def target(**amounts):
    landmarks = np.full((478, 3), .5, np.float32)
    return {'_enhance': {'amounts': amounts, 'built': True, 'box': (.1, .1, .6, .6)},
            '_enhance_defer': False, '_face_box': (.2, .2, .8, .8), '_face_explicit': True,
            '_precompute': SimpleNamespace(backend='mediapipe', landmarks=landmarks, num_faces=1),
            '_effect_recovery': {'target_only_fixture': 'do not copy source assets'}}


def test_scope_is_registered_and_partial_old_recipes_leave_new_controls_neutral():
    assert E.OP == A.ENHANCE == 'lnx.enhance.v1'
    assert SC.MODULES[E.OP]['read'] is E.params_of
    assert SC.MODULES[E.OP]['write'] is E.install
    checked = SC.check_params(E.OP, recipe(teeth=.4))['recipe']['amounts']
    assert checked['teeth'] == .4
    assert checked['teeth_brightness'] == checked['teeth_yellow_removal'] == 0
    assert '/teeth_brightness' in A.defaults()[E.OP]
    assert '/teeth_yellow_removal' in A.defaults()[E.OP]


def test_scope_changes_only_its_amounts_and_always_rebuilds_target_support():
    state = target(teeth=.3, iris=.2, wrinkle_cheek=.4)
    prior = deepcopy(state['_effect_recovery']); pc = state['_precompute']
    E.install(state, recipe(teeth=.3, iris=.2, teeth_brightness=.55, teeth_yellow_removal=.7))
    amounts = state['_enhance']['amounts']
    assert amounts['teeth'] == .3 and amounts['iris'] == .2 and amounts['wrinkle_cheek'] == .4
    assert amounts['teeth_brightness'] == .55 and amounts['teeth_yellow_removal'] == .7
    assert state['_enhance']['box'] == (.2, .2, .8, .8)
    assert not state['_enhance']['built'] and state['_enhance_defer'] is True
    assert state['_precompute'] is pc and state['_effect_recovery'] == prior
    exported = E.params_of(state)
    assert set(exported) == {'recipe'} and set(exported['recipe']) == {'version', 'amounts'}
    assert 'wrinkle_cheek' not in exported['recipe']['amounts']
    assert set(exported['recipe']['amounts']) == set(A.check_enhance({}))


def test_neutral_scope_needs_no_analysis_and_does_not_enable_a_layer():
    state = {'_enhance': {'amounts': {'teeth': 0}, 'built': False, 'box': None}}
    E.install(state, recipe())
    assert not state['_enhance_defer'] and not state['_enhance']['built']
    assert state['_enhance']['box'] is None
    assert not any(state['_enhance']['amounts'].values())


@pytest.mark.parametrize('bad', [True, False, None, '0.5', float('nan'), float('inf'), -.01, 1.01, 10**1000])
@pytest.mark.parametrize('key', ['teeth_brightness', 'teeth_yellow_removal'])
def test_invalid_independent_scalar_rejects_before_state_mutation(key, bad):
    state = target(teeth=.4); before = deepcopy(state['_enhance'])
    with pytest.raises(ValueError): E.install(state, recipe(**{key: bad}))
    assert state['_enhance'] == before and state['_enhance_defer'] is False


@pytest.mark.parametrize('field,value', [('mask', []), ('face_ref', {}), ('wrinkle_cheek', .5)])
def test_source_assets_and_other_canonical_owners_cannot_enter_scalar_recipe(field, value):
    with pytest.raises(ValueError): E.check_params(recipe(**{field: value}))
    with pytest.raises(ValueError): E.check_params({**recipe(teeth_brightness=.2), field: value})


@pytest.mark.parametrize('fault', ['no-analysis', 'synthetic', 'ambiguous', 'no-target-box'])
def test_active_transfer_requires_target_owned_analysis_and_unambiguous_face(fault):
    state = target(teeth=.4); before = deepcopy(state['_enhance'])
    if fault == 'no-analysis': state['_precompute'] = None
    elif fault == 'synthetic': state['_precompute'].backend = 'synthetic'
    elif fault == 'ambiguous': state['_precompute'].num_faces = 2; state['_face_explicit'] = False
    else: state['_face_box'] = None
    with pytest.raises(ValueError): E.install(state, recipe(teeth_brightness=.6))
    assert state['_enhance'] == before


def test_derived_generic_scope_refuses_before_using_original_file_analysis(monkeypatch):
    import struct
    from lumaretouch_engine.creative_document_assets import make_asset
    state = target(teeth=.4); before = deepcopy(state['_enhance'])
    state['_creative_base'] = make_asset('rgba', 1, 1, struct.pack('<ffff', .2, .2, .2, 1.))
    monkeypatch.setattr(H, '_landmark_pixels', lambda *_: pytest.fail('Used original-file analysis'))
    with pytest.raises(ValueError, match='人物参数映射'): E.install(state, recipe(teeth_brightness=.5))
    with pytest.raises(SC.ScopeError): SC.apply_modules(state, {E.OP: recipe(teeth_brightness=.5)})
    assert state['_enhance'] == before


def graph():
    state = S.empty()
    evidence = {'backend': 'authored_fixture', 'detector_model_sha256': 'b' * 64,
        'semantic_model_sha256': None, 'landmark_digest': 'c' * 64, 'status': 'verified',
        'source_width': 640, 'source_height': 480, 'orientation': 'exif_normalized_once'}
    face = S.new_face(ASSET, [.1, .2, .6, .8], evidence); face['face_instance_id'] = FACE
    face['local_assets']['target-support'] = {'owner': S.face_ref(face), 'content_sha256': 'd' * 64, 'kind': 'fixture'}
    state['faces'][FACE] = face
    state['groups']['group'] = {'label': 'Preserve target group', 'priority': 1, 'face_ids': [FACE]}
    state = S.set_override(state, 'group', 'group', A.ENHANCE, '/sclera', .2)
    return S.set_override(state, 'face', FACE, A.ENHANCE, '/teeth', .3)


class Owner:
    def __init__(self, state):
        self.state = S.check(state); self.fence = 0; self.association_fence = state['association_revision']; self.commits = []
    def snapshot(self): return deepcopy(self.state)
    def commit(self, state, *, expected_fence):
        assert expected_fence == self.fence
        self.state = S.check(state); self.commits.append(deepcopy(state)); self.fence += 1


def replay_engine(monkeypatch, *, fail=False):
    from lumaretouch_engine import eye_light_scope, blush_makeup_scope, lipstick_scope, eyeliner_scope
    from lumaretouch_engine import eyelash_scope, brow_makeup_scope, iris_makeup_scope
    current = {'_enhance': {'amounts': H.check_amounts({'teeth': .3, 'sclera': .2}), 'built': True, 'box': (.1, .2, .6, .8)}}
    owner = Owner(graph()); replays = []
    engine = SimpleNamespace(_people_managed=lambda: True, _people_owner=lambda: owner,
        _people_source=lambda: {'sha256': ASSET}, _people_analysis_key='old', current=current)
    monkeypatch.setattr(eye_light_scope, 'capture', lambda engine: deepcopy(engine.current))
    for module in (blush_makeup_scope, lipstick_scope, eyeliner_scope, eyelash_scope, brow_makeup_scope, iris_makeup_scope):
        monkeypatch.setattr(module, 'capture', lambda engine, base: base)
    def replay(state, **kwargs):
        replays.append((deepcopy(state), kwargs))
        if fail: raise RuntimeError('authored target-render refusal')
        return {'render_ms': 0}
    engine._replay_state = replay
    return engine, owner, replays


def test_preset_replays_independent_leaves_into_existing_face_owner(monkeypatch):
    engine, owner, replays = replay_engine(monkeypatch)
    before = owner.snapshot(); candidate = deepcopy(engine.current)
    candidate['_enhance']['amounts'].update(teeth_brightness=.45, teeth_yellow_removal=.7)
    P.replay_preset(engine, candidate, mode='preset', replayed_for='fixture')
    after = owner.snapshot()
    for field in ('faces', 'groups', 'persons', 'links', 'analysis_runs', 'unresolved_legacy'):
        assert after[field] == before[field]
    for override in before['overrides']: assert override in after['overrides']
    changes = [row for row in after['overrides'] if row not in before['overrides']]
    assert {(r['operation_id'], r['parameter_path'], r['value']) for r in changes} == {
        (A.ENHANCE, '/teeth_brightness', .45), (A.ENHANCE, '/teeth_yellow_removal', .7)}
    assert all(row['scope'] == 'face' and row['target_id'] == FACE for row in changes)
    assert replays[0][1]['strict_local'] is True


def test_old_project_absent_independent_leaves_are_a_noop(monkeypatch):
    engine, owner, replays = replay_engine(monkeypatch)
    engine.current['_enhance']['amounts'].pop('teeth_brightness')
    engine.current['_enhance']['amounts'].pop('teeth_yellow_removal')
    P.replay_preset(engine, deepcopy(engine.current), mode='preset', replayed_for='fixture')
    assert not owner.commits and len(replays) == 1


def test_ambiguous_face_or_invalid_scalar_never_commits(monkeypatch):
    engine, owner, replays = replay_engine(monkeypatch)
    candidate = deepcopy(engine.current); candidate['_enhance']['amounts']['teeth_brightness'] = .4
    another = deepcopy(owner.state['faces'][FACE]); another['face_instance_id'] = 'second'; another['local_assets'] = {}
    owner.state['faces']['second'] = another
    with pytest.raises(ValueError, match='unambiguous'): P.replay_preset(engine, candidate)
    assert not owner.commits and not replays
    owner.state['faces'].pop('second'); candidate['_enhance']['amounts']['teeth_brightness'] = float('nan')
    with pytest.raises(ValueError): P.replay_preset(engine, candidate)
    assert not owner.commits and not replays


def test_replay_refusal_restores_exact_prior_people_graph(monkeypatch):
    engine, owner, _ = replay_engine(monkeypatch, fail=True)
    before = owner.snapshot(); candidate = deepcopy(engine.current)
    candidate['_enhance']['amounts']['teeth_yellow_removal'] = .7
    with pytest.raises(RuntimeError, match='target-render refusal'): P.replay_preset(engine, candidate)
    assert owner.snapshot() == before and len(owner.commits) == 2


def test_unmanaged_or_unchanged_active_independent_layer_still_requires_strict_replay(monkeypatch):
    engine, owner, replays = replay_engine(monkeypatch)
    engine.current['_enhance']['amounts']['teeth_brightness'] = .5
    state = deepcopy(engine.current)
    P.replay_preset(engine, state)
    assert not owner.commits and replays[-1][1]['strict_local'] is True
    engine._people_managed = lambda: False
    P.replay_preset(engine, state)
    assert not owner.commits and replays[-1][1]['strict_local'] is True
