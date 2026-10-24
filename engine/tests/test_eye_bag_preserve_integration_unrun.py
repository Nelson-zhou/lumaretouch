# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: dormant intent, staged deltas, project and export wiring.

No tests, product imports, inference or runtime/native acceptance was performed.
Synthetic deltas are arithmetic contracts, not eye-bag photographic quality.
"""
import ast
from copy import deepcopy
from pathlib import Path
import numpy as np
import pytest
from lumaretouch_engine import people_algorithms as A, people_state as P
from lumaretouch_engine import people_render_plan as PLAN, people_effects as E
from lumaretouch_engine import people_project as PROJECT, people_export as EXPORT
from lumaretouch_engine import eye_bag_preserve_state as S
from test_eye_bag_preserve_scope_unrun import ASSET, FACE, graph

ROOT = Path(__file__).resolve().parents[1] / 'src/lumaretouch_engine'


@pytest.mark.parametrize('preserve', [0., .25, 1.])
@pytest.mark.parametrize('retained_review', [False, True])
def test_amount_zero_remains_dormant_with_or_without_retained_review(preserve, retained_review):
    state = graph(); state = P.set_override(state, 'face', FACE, S.OP, '/preserve', preserve)
    if retained_review:
        face = state['faces'][FACE]
        face['local_assets'][S.KIND] = {'owner': P.face_ref(face), 'kind': S.KIND, 'content_sha256': 'e' * 64}
    plan = PLAN.build(state, ASSET, A.defaults(), max_faces=0, per_face_cost=1,
        total_budget=0, available_evidence={}, operation_check=lambda face, resolved: [])
    assert plan['entries'][0]['requires_analysis'] is False
    assert plan['entries'][0]['status'] == 'ready' and plan['budget_used'] == 0


def test_active_amount_cannot_bypass_missing_analysis_with_preserve_one():
    state = P.set_override(graph(), 'face', FACE, S.OP, '/amount', .4)
    plan = PLAN.build(state, ASSET, A.defaults(), max_faces=2, per_face_cost=1,
        total_budget=2, available_evidence={}, operation_check=lambda face, resolved: [])
    assert plan['entries'][0]['requires_analysis'] is True
    assert plan['entries'][0]['status'] == 'refused'


@pytest.mark.parametrize('path,value', [('/amount', True), ('/preserve', False),
    ('/preserve', float('nan')), ('/preserve', 1.1), ('/mask', 0.)])
def test_persisted_invalid_v2_leaf_cannot_hide_in_empty_all_people_scope(path, value):
    state = P.empty()
    # Nonfinite input may already be refused by the generic scalar validator.
    with pytest.raises(ValueError):
        state = P.set_override(state, 'all_people', ASSET, S.OP, path, value)
        PROJECT.validate_records({'people_graph': state})


def test_historical_v1_and_v2_conflict_remains_readable_for_explicit_recovery():
    state = P.set_override(graph(), 'face', FACE, A.ENHANCE, '/eye_bags', .6)
    state = P.set_override(state, 'face', FACE, S.OP, '/amount', .3)
    before = deepcopy(state)
    PROJECT.validate_records({'people_graph': state, 'undo': [{'_people_state': state}]})
    assert state == before
    assert EXPORT.fastpath_blocker({'state': state, 'asset_sha256': ASSET}) is True


def record(stage, delta):
    state = graph()
    return E.LocalEffect(P.face_ref(state['faces'][FACE]), stage, (0, 0, 2, 2), delta=delta,
                         facts={'synthetic_contract_only': True})


def test_distinct_stage_preserves_overlapping_eye_detail_and_zero_protected_delta():
    source = np.full((2, 2, 3), .4, np.float32)
    old = np.zeros_like(source); old[..., 0] = .1
    bag = np.zeros_like(source); bag[..., 1] = .2
    records = [record('eye_detail', old), record('eye_bag_preserve', bag)]
    out, _ = E.apply('eye_detail', source, records)
    result, facts = E.apply('eye_bag_preserve', out, records)
    np.testing.assert_allclose(result, source + old + bag, rtol=0, atol=1e-7)
    assert facts['stage'] == 'eye_bag_preserve'
    protected, _ = E.apply('eye_bag_preserve', out, [record('eye_bag_preserve', np.zeros_like(source))])
    np.testing.assert_array_equal(protected, out)


def test_new_composition_scales_vector_to_headroom_without_channel_clipping():
    source = np.full((2, 2, 3), .5, np.float32); source[..., 0] = .95
    delta = np.zeros_like(source); delta[..., 0] = .2; delta[..., 1] = .1
    out, facts = E.apply('eye_bag_preserve', source, [record('eye_bag_preserve', delta)])
    gain = (out - source)[..., :2] / delta[..., :2]
    np.testing.assert_allclose(gain[..., 0], gain[..., 1], atol=1e-6)
    assert np.all(out <= 1) and np.all(gain < 1)
    assert 'no-channel-clipping' in facts['composition']


def test_active_hdr_composition_refuses_instead_of_clipping():
    source = np.full((2, 2, 3), 1.1, np.float32)
    delta = np.full_like(source, -.05)
    with pytest.raises(ValueError, match='HDR'):
        E.apply('eye_bag_preserve', source, [record('eye_bag_preserve', delta)])


def test_preview_and_export_forward_target_bank_and_solver_stays_before_tiles():
    runtime = ast.parse((ROOT / 'people_engine_runtime.py').read_text())
    for name in ('prepare_preview', 'synchronize'):
        function = next(node for node in runtime.body if isinstance(node, ast.FunctionDef) and node.name == name)
        assert 'eye_bag_preserve_assets' in [arg.arg for arg in function.args.kwonlyargs]
    source = (ROOT / 'people_engine_runtime.py').read_text()
    assert "eye_bag_preserve_assets=snapshot.get('support_assets',{})" in source
    inputs = (ROOT / 'people_owned_inputs.py').read_text()
    assert inputs.count("'eye_bag_preserve_assets':") == 2
    pipeline = (ROOT / 'people_pipeline.py').read_text()
    assert pipeline.index("delta=_merge_delta(pipe,'eye_detail',align=True)") < pipeline.index("delta=_merge_delta(pipe,'eye_bag_preserve',align=True)")
    assert 'prepare_eye_bag_preserve' not in pipeline
    assert "out=apply_t(out,delta,label='Eye-bag preservation')" in pipeline


def test_project_history_and_support_bank_use_dedicated_validators():
    project = (ROOT / 'people_project.py').read_text()
    assert 'validate_eye_bag_graph(value[key])' in project
    assert 'validate_eye_bag_support(value)' in project
    store = (ROOT / 'people_support_assets.py').read_text()
    assert 'from .eye_bag_preserve_support import check_record' in store
    assert "'eye_bag_ridge_visibility'):continue # Dedicated support consumers" in store


def test_derived_review_actions_use_exact_dedicated_structural_admission():
    source = (ROOT / 'creative_derived_effects.py').read_text()
    assert "('eye_bag_reference','eye_bag_preview','eye_bag_image','eye_bag_confirm')" in source
    assert 'from .eye_bag_preserve_host import check_action' in source
    assert "'lnx.eye_bags.v2'" in source
    assert "'eye_bag_ridge_visibility'" in source
