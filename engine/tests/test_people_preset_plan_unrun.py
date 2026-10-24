# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: shared mixed portrait planner and exact graph publication.

Mocked renderer/target fixtures test ownership contracts only. No imports,
collection, tests, native execution or photographic acceptance ran to author.
"""
from copy import deepcopy
from pathlib import Path
import ast
import pytest
from lumaretouch_engine import people_scope as R, people_preset_plan as P
from lumaretouch_engine import people_state as S
from test_philtrum_scope_unrun import replay_fixture, put, recipe, C, FACE, A


def prepared(monkeypatch, amount=.3):
    engine, owner, analysis, current, calls = replay_fixture(monkeypatch)
    engine._people_active_context = {'owner': owner}
    engine._people_graph_owner = owner; engine._people_scope_row = engine._docs[0]
    state = C.capture(engine); C.install(state, recipe(amount))
    state['_exposure'] = .4; state['_crop_rect'] = [.1, .1, .9, .9]
    return engine, owner, analysis, state, calls


def test_plan_does_not_publish_or_render_and_preserves_complete_nonpeople_state(monkeypatch):
    engine, owner, analysis, state, calls = prepared(monkeypatch)
    prior = owner.snapshot(); source = deepcopy(state)
    plan = R.plan_preset(engine, state)
    assert owner.snapshot() == prior and not owner.commits and not calls and state == source
    assert plan.before == prior and plan.candidate != prior and plan.patches
    assert plan.state['_exposure'] == .4 and plan.state['_crop_rect'] == [.1, .1, .9, .9]
    assert plan.target_ref == S.face_ref(prior['faces'][FACE]) and plan.kwargs['strict_local'] is True
    assert engine._people_analyses[next(iter(engine._people_analyses))][FACE] is analysis


def test_exact_consumer_does_not_restage_a_second_partial_graph(monkeypatch):
    engine, owner, _, state, calls = prepared(monkeypatch)
    plan = R.plan_preset(engine, state)
    monkeypatch.setattr(R, 'plan_preset', lambda *a, **k: (_ for _ in ()).throw(AssertionError('restaged')))
    result = R.execute_plan(engine, plan)
    assert result == {'event': 'frame'} and owner.snapshot() == plan.candidate
    assert len(owner.commits) == 1 and calls[0][0]['_exposure'] == .4


def test_planner_preserves_other_retained_operations_and_uses_existing_target(monkeypatch):
    engine, owner, _, state, _ = prepared(monkeypatch)
    owner.value = S.set_override(owner.value, 'group', 'preserved', A.DEFORM, '/small_chin', -.4)
    plan = R.plan_preset(engine, state)
    assert all(leaf in plan.candidate['overrides'] for leaf in plan.before['overrides'])
    added = [leaf for leaf in plan.candidate['overrides'] if leaf not in plan.before['overrides']]
    assert added == [{'scope': 'face', 'target_id': FACE, 'operation_id': C.OP,
                      'parameter_path': '/amount', 'value': .3}]


def test_unchanged_active_plan_is_nonmutating_but_strict_and_still_renders(monkeypatch):
    engine, owner, _, _, calls = prepared(monkeypatch); put(owner, .3)
    plan = R.plan_preset(engine, C.capture(engine))
    assert not plan.patches and plan.before == plan.candidate and plan.kwargs['strict_local'] is True
    R.execute_plan(engine, plan, strict_local=False)
    assert not owner.commits and calls[-1][1]['strict_local'] is True


def test_preview_refuses_lazy_owner_activation_before_any_capture(monkeypatch):
    engine, owner, _, state, calls = prepared(monkeypatch)
    del engine._people_active_context
    def forbidden(): raise AssertionError('lazy owner activation')
    engine._people_owner = forbidden
    with pytest.raises(ValueError, match='existing active'): R.plan_preset(engine, state)
    assert not owner.commits and not calls


def test_mutated_owner_after_plan_cannot_publish_or_rollback_foreign_state(monkeypatch):
    engine, owner, _, state, calls = prepared(monkeypatch); plan = R.plan_preset(engine, state)
    other = S.set_override(owner.snapshot(), 'face', FACE, A.DEFORM, '/slim_face', .1)
    owner.commit(other, expected_fence=owner.fence); commits = len(owner.commits)
    with pytest.raises(ValueError, match='changed after'): R.execute_plan(engine, plan)
    assert owner.snapshot() == other and len(owner.commits) == commits and not calls


def test_failure_after_graph_publish_restores_exact_before_graph(monkeypatch):
    engine, owner, _, state, _ = prepared(monkeypatch); plan = R.plan_preset(engine, state)
    def failed(*a, **k): raise RuntimeError('render refused')
    engine._replay_state = failed
    with pytest.raises(RuntimeError, match='render refused'): R.execute_plan(engine, plan)
    assert owner.snapshot() == plan.before and len(owner.commits) == 2


def test_explicit_restore_uses_frozen_before_not_reverse_scalar_diff(monkeypatch):
    engine, owner, _, state, calls = prepared(monkeypatch); before_state = C.capture(engine)
    before_state['_exposure'] = -.2
    plan = R.plan_preset(engine, state); R.execute_plan(engine, plan)
    R.restore_plan(engine, plan, before_state, expected_owner_fence=owner.fence)
    assert P.graph_content(owner.snapshot()) == P.graph_content(plan.before)
    assert calls[-1][0]['_exposure'] == -.2 and len(owner.commits) == 2


def test_restore_refuses_another_graph_and_requires_optional_exact_fence(monkeypatch):
    engine, owner, _, state, _ = prepared(monkeypatch); plan = R.plan_preset(engine, state)
    R.execute_plan(engine, plan)
    with pytest.raises(ValueError, match='changed before'): R.restore_plan(engine, plan, {}, expected_owner_fence=-1)
    owner.value = S.set_override(owner.value, 'face', FACE, A.DEFORM, '/slim_face', .2)
    prior = owner.snapshot()
    with pytest.raises(ValueError, match='unrelated'): R.restore_plan(engine, plan, {})
    assert owner.snapshot() == prior


def test_only_top_level_bookkeeping_is_normalized(monkeypatch):
    _, owner, _, _, _ = prepared(monkeypatch); before = owner.snapshot(); candidate = deepcopy(before)
    candidate['revision'] += 3; candidate['association_revision'] += 2
    assert P.graph_content(candidate) == P.graph_content(before)
    candidate['faces'][FACE]['analysis_revision'] += 1
    for support in candidate['faces'][FACE]['local_assets'].values():
        support['owner'] = S.face_ref(candidate['faces'][FACE])
    assert P.graph_content(candidate) != P.graph_content(before)


def test_recipe_containers_copy_but_opaque_runtime_buffers_are_not_duplicated():
    class ImmutableBuffer:
        def __deepcopy__(self, memo): raise AssertionError('full-source buffer copy')
    buffer = ImmutableBuffer(); value = {'recipe': {'points': [[.1, .2]]}, 'buffer': buffer}
    copy = P.clone_state(value)
    assert copy['buffer'] is buffer and copy['recipe'] is not value['recipe']
    copy['recipe']['points'][0][0] = .3
    assert value['recipe']['points'][0][0] == .1


def test_legacy_unmanaged_path_stays_explicit_and_nonpublishing(monkeypatch):
    engine, owner, _, _, calls = prepared(monkeypatch); engine._people_managed = lambda: False
    plan = R.plan_preset(engine, {'_exposure': .5})
    assert not plan.managed and plan.before is None and plan.candidate is None and not calls
    R.execute_plan(engine, plan)
    assert calls[-1][0]['_exposure'] == .5 and not owner.commits


def test_planning_function_has_no_commit_live_replay_or_render_calls():
    module = ast.parse((Path(__file__).resolve().parents[1] / 'src/lumaretouch_engine/people_scope.py').read_text())
    plan = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'plan_preset')
    names = {node.func.attr for node in ast.walk(plan) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not names & {'commit', '_replay_state', 'render', '_people_bind'}
    replay = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'replay_preset')
    called = {node.func.id for node in ast.walk(replay) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert {'plan_preset', 'execute_plan'} <= called


def test_real_owner_monotonic_counters_do_not_prevent_exact_restore(monkeypatch):
    from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
    engine, fixture_owner, _, state, calls = prepared(monkeypatch)
    owner = PeopleGraphOwner(fixture_owner.snapshot())
    engine._people_owner = lambda: owner
    engine._people_active_context = {'owner': owner}; engine._people_graph_owner = owner
    plan = R.plan_preset(engine, state)
    R.execute_plan(engine, plan)
    assert owner.snapshot()['revision'] > plan.candidate['revision']
    R.restore_plan(engine, plan, {'_exposure': -.1}, expected_owner_fence=owner.fence)
    assert P.graph_content(owner.snapshot()) == P.graph_content(plan.before)
    assert owner.snapshot()['revision'] > plan.before['revision'] and calls[-1][0]['_exposure'] == -.1
