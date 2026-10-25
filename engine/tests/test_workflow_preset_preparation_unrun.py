"""Authored UNRUN: ownership/transport doubles, not actual analysis or pixels."""
from copy import deepcopy
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import workflow_preset_preparation as P
from lumaretouch_engine import workflow_preset_retained_skin as K
from lumaretouch_engine import people_state as S, people_binding as B
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner


@dataclass
class Analysis:
    backend: str = 'mediapipe'
    num_faces: int = 1
    masks: dict = field(default_factory=lambda: {'skin': np.ones((2, 2), dtype=np.float32)})
    landmarks: object = field(default_factory=lambda: np.zeros((478, 3), dtype=np.float32))
    detector_model_sha256: str = 'b' * 64
    semantic_model_sha256: str = 'c' * 64


@pytest.fixture
def retained(monkeypatch):
    asset = 'a' * 64
    pc = Analysis()
    row = {'document_id': 'target', 'copy_number': 0, 'src_w': 20, 'src_h': 20}
    evidence = B.evidence(pc, pc.landmarks, (20, 20))
    face = S.new_face(asset, [0.1, 0.1, 0.9, 0.9], evidence)
    ref = S.face_ref(face)
    graph = S.empty()
    graph['faces'][ref['face_instance_id']] = face
    graph['analysis_runs'][asset] = {'detector_limit': 32, 'limit_reached': False,
        'census_complete': False, 'notice': 'Detection does not prove a complete census'}
    owner = PeopleGraphOwner(graph)
    engine = SimpleNamespace(_docs=[row], _doc_index=0, _load_id='load', _people_scope_row=row,
        _people_graph_owner=owner, _people_active_context={'owner': owner},
        _people_cursors={asset: ref['face_instance_id']},
        _people_targets={asset: {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}},
        _people_analyses={asset: {ref['face_instance_id']: {'face_ref': ref, 'evidence': evidence,
            'landmarks': pc.landmarks, 'skin': pc.masks['skin']}}})
    before = {'_creative_base': None, '_precompute': pc, '_channel': 'skin', '_strength': 0.0}
    engine._people_preset_capture = lambda: before
    monkeypatch.setattr(K.SOURCE, 'row_proof', lambda _: {'asset_sha256': asset})
    monkeypatch.setattr(K.SOURCE, 'verify_precompute', lambda *_: None)
    return SimpleNamespace(engine=engine, row=row, before=before, owner=owner, graph=graph,
                           face=face, ref=ref, pc=pc, asset=asset)


def test_exact_target_retained_analysis_is_admitted_without_mutation(retained):
    f = retained
    before = f.owner.snapshot()
    assert K.require_target(f.engine, f.row, f.before) == (f.owner, before, f.ref)
    assert f.owner.snapshot() == before and f.owner.fence == 0


@pytest.mark.parametrize('count', [0, 2, True, None, '1'])
def test_no_zero_multiple_or_unknown_face_approval(retained, count):
    retained.pc.num_faces = count
    with pytest.raises(ValueError, match='exactly one'):
        K.require_target(retained.engine, retained.row, retained.before)


@pytest.mark.parametrize('kind', ['backend', 'channel', 'mask', 'cursor', 'target', 'limit', 'manual', 'disabled', 'stale_analysis'])
def test_retained_face_and_actual_selected_mask_must_agree(retained, kind):
    f = retained
    if kind == 'backend': f.pc.backend = 'synthetic'
    elif kind == 'channel': f.before['_channel'] = None
    elif kind == 'mask': f.pc.masks.clear()
    elif kind == 'cursor': f.engine._people_cursors[f.asset] = 'another-face'
    elif kind == 'target': f.engine._people_targets[f.asset]['face_ref'] = {**f.ref, 'analysis_revision': 99}
    elif kind == 'stale_analysis': f.engine._people_analyses[f.asset][f.ref['face_instance_id']]['face_ref'] = {**f.ref, 'analysis_revision': 99}
    else:
        graph = f.owner.snapshot()
        if kind == 'limit': graph['analysis_runs'][f.asset]['limit_reached'] = True
        elif kind == 'manual': graph['faces'][f.ref['face_instance_id']]['manual'] = True
        else: graph['faces'][f.ref['face_instance_id']]['enabled'] = False
        f.owner.commit(graph, expected_fence=0)
    with pytest.raises(ValueError): K.require_target(f.engine, f.row, f.before)


def test_candidate_requires_same_normal_people_plan_and_no_graph_patch(retained, monkeypatch):
    from lumaretouch_engine import people_scope
    f = retained
    after = {**f.before, '_strength': 0.35}
    plan = SimpleNamespace(managed=True, owner=f.owner, owner_fence=0, before=f.graph,
        candidate=f.graph, patches=(), target_ref=f.ref, state=after)
    calls = []
    def prepare(engine, state):
        calls.append((engine, state))
        return plan
    monkeypatch.setattr(people_scope, 'plan_preset', prepare)
    assert K.require_candidate(f.engine, f.row, f.before, after) is plan
    assert calls == [(f.engine, after)]
    plan.patches = (('unrequested-operation', '/amount', 1.0),)
    with pytest.raises(ValueError, match='Canonical people preset plan'):
        K.require_candidate(f.engine, f.row, f.before, after)


def test_fresh_guard_uses_complete_canonical_state_not_only_zero_strength():
    baseline = {'_strength': 0.0, '_channel': None, '_proxy': None, '_unrelated': 0.0}
    live = {**baseline, '_proxy': (20, 20)}
    engine = SimpleNamespace(_project_dirty=False, _undo=[], _redo=[], _creative_base=None,
        _capture_state=lambda: dict(live), _fresh_doc_state=lambda: dict(baseline))
    assert P.require_fresh(engine, {}) == live
    live['_unrelated'] = 0.1
    with pytest.raises(ValueError, match='edited'): P.require_fresh(engine, {})
    live['_unrelated'] = 0.0
    engine._undo.append({'ordinary_edit': True})
    with pytest.raises(ValueError, match='undo/redo'): P.require_fresh(engine, {})
    engine._undo.clear()
    engine._project_recovery_runtime = SimpleNamespace(tainted=True)
    with pytest.raises(ValueError, match='recovery boundary'): P.require_fresh(engine, {})


def test_preparation_cannot_repeat_an_inference_attempt():
    value = P.SkinPreparation.__new__(P.SkinPreparation)
    value.started, value.restored = True, False
    with pytest.raises(ValueError, match='redispatched'): value.analyse()


def test_explicit_analysis_uses_exact_dispatch_then_canonical_sync(monkeypatch):
    calls = []
    value = P.SkinPreparation.__new__(P.SkinPreparation)
    value.started = value.restored = value.ready = False
    value.initial = ('same-owned-target',)
    value._proof = lambda: ('same-owned-target',)
    value._check = lambda: None
    value._target_only = lambda: calls.append('target-slice-check')
    value.row = {}
    value.before = {'_deform': {'amounts': {}}, '_enhance': {'amounts': {}},
                    '_precompute': None, '_channel': None}
    pc = Analysis()
    after = {**value.before, '_precompute': pc, '_channel': 'skin'}
    engine = SimpleNamespace(_precompute=None, _channel=None,
        _capture_state=lambda: after, _people_preset_capture=lambda: after,
        _people_sync=lambda **kwargs: calls.append(('canonical-sync', kwargs)))
    value.engine = engine
    def dispatch(actual, command, check):
        check()
        assert actual is engine
        calls.append(('dispatch', dict(command)))
        engine._precompute, engine._channel = pc, 'skin'
    monkeypatch.setattr(P, 'dispatch', dispatch)
    monkeypatch.setattr(K, 'require_target', lambda *_: calls.append('retained-target-check'))
    value.analyse()
    assert calls == [('dispatch', {'cmd': 'precompute', 'backend': 'mediapipe', 'channel': 'skin'}),
                     ('canonical-sync', {'strict': True}), 'target-slice-check', 'retained-target-check']
    assert value.ready and value.started and value.expected == ('same-owned-target',)


def test_cancel_reuses_canonical_slice_and_state_owners_without_history_rewrite(monkeypatch):
    import sys
    calls = []
    value = P.SkinPreparation.__new__(P.SkinPreparation)
    value.started, value.restored, value.expected = True, False, ('exact-observation',)
    value._proof = lambda: ('exact-observation',)
    value._check = lambda: None
    value._target_only = lambda: calls.append('target-slice-check')
    value.before = {'_precompute': None, '_channel': None, '_strength': 0.0}
    value.slice = {'asset_sha256': 'a' * 64}
    value.graph = S.empty()
    value.owner = SimpleNamespace(snapshot=lambda: deepcopy(value.graph))
    value.runtime = {'analyses': {}, **{key: {} for key in P.V.FIELDS}}
    engine = SimpleNamespace(_undo=[], _redo=[],
        _people_history_apply=lambda snapshot, **kwargs: calls.append(('canonical-history', snapshot, kwargs)),
        _fence_current_document=lambda: calls.append('advance-fence'),
        _replay_state=lambda state, **kwargs: (calls.append(('canonical-replay', state, kwargs)), {'event': 'frame'})[1],
        _capture_state=lambda: deepcopy(value.before),
        _remember_current=lambda: calls.append('remember'), emit_session_state=lambda: calls.append('state-event'))
    value.engine = engine
    monkeypatch.setitem(sys.modules, 'lumaretouch_engine.server', SimpleNamespace(emit=lambda frame: calls.append(('emit', frame))))
    value.restore()
    assert calls[0] == 'target-slice-check'
    assert calls[1][0] == 'canonical-history' and calls[1][1] == value.slice
    assert calls[2] == 'advance-fence' and calls[3][0] == 'canonical-replay'
    assert calls[3][1] == value.before and calls[3][1]['_precompute'] is None
    assert value.restored and engine._undo == [] and engine._redo == []


def test_cancellation_refuses_changed_state_before_any_restoration():
    value = P.SkinPreparation.__new__(P.SkinPreparation)
    value.started, value.restored, value.expected = True, False, ('original-observation',)
    value._proof = lambda: ('newer-edit',)
    with pytest.raises(ValueError, match='must not overwrite'): value.restore()


def test_unknown_preparation_has_no_cancel_authority():
    value = P.SkinPreparation.__new__(P.SkinPreparation)
    value.started, value.restored, value.expected = True, False, None
    with pytest.raises(ValueError, match='No exact'): value.restore()
