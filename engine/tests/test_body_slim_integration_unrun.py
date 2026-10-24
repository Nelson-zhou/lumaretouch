# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Static route guards and neutral compatibility fixtures."""
from pathlib import Path
from lumaretouch_engine import body_pose_state as B
from lumaretouch_engine import body_pose_geometry as G
from lumaretouch_engine import body_slim_runtime as R

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/src/lumaretouch_engine'


def test_absent_family_keeps_old_order_and_does_not_require_new_budget():
    bank = B.empty()
    assert G.effective_order(bank) == G.DEFAULT_BODY_ORDER
    assert R.prepare_fields(bank, 'a'*64, (1, 1), byte_budget=0) == ()


def test_single_common_sampler_and_exact_source_path():
    source = (ENGINE / 'body_pose_render.py').read_text()
    assert source.count('body_slim.prepare_fields(') == 1
    assert 'byte_budget=remaining,source_frame=frame' in source
    assert source.count('wrapper=A.prepare_common(') == 1
    project = (ENGINE / 'body_slim_project.py').read_text()
    assert 'from .body_pose_geometry import BODY_SLIM_BODY_ORDER' in project
    assert 'FrozenBodyOrder(' not in project


def test_missing_core_and_unapplied_publication_are_not_rendered_success():
    source = (ENGINE / 'body_slim_host.py').read_text()
    assert "requires_core=(action=='recipe' and S.active(payload['recipe']))" in source
    assert "action=='operation_status' and payload['enabled'] is True" in source
    assert 'if requires_core: raise' in source
    assert 'not publication[\'rendered\'] and (type(reason) is not str' in source
    assert "'view':deepcopy(authoritative)" in source


def test_actual_native_route_and_retained_job_identity():
    native = ROOT / 'ui/src-tauri/src'
    assert 'body_slim_api::body_slim' in (native / 'main.rs').read_text()
    assert 'body_slim_api::guards_result(inspection_epoch,id)' in (native / 'engine.rs').read_text()
    assert 'body_slim_api::enqueue(handle, cmd)' in (native / 'native_dispatch.rs').read_text()
    assert 'bodySlim={bodySlim}' in (ROOT / 'ui/src/App.tsx').read_text()
    assert 'data-tool-anchor="瘦身"' in (ROOT / 'ui/src/bodySlim/BodySlimLaunch.tsx').read_text()


def test_read_queries_do_not_cancel_another_arm_proposal():
    source = (ENGINE / 'arm_shape_registered_host.py').read_text()
    assert "'head_size','body_slim') and action in ('view','select','status'):return" in source
