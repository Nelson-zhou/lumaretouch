# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED UNRUN. Registration/source contracts, not photographic acceptance."""
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ENGINE=ROOT/'engine/src/lumaretouch_engine'


def source(name):return (ENGINE/name).read_text()


def test_registered_arm_policy_is_not_a_replacement_body_bank():
    value=source('body_pose_operations.py')
    assert 'arm_shape_state as A' in value and '**A.policies()' in value
    assert "KEY='_body_pose_bank'" in source('body_pose_project.py')
    assert 'lrt.project.v14' in source('project.py')
    assert '_arm_pose_bank' not in source('body_pose_host.py')


def test_one_common_order_preserves_neutral_versions():
    value=source('body_pose_geometry.py')
    assert 'PORTRAIT_BODY_ORDER=FrozenBodyOrder(3,(*LEG_BODY_ORDER.operation_ids,*ARM_OPERATION_IDS))' in value
    tree=ast.parse(value);fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='effective_order')
    names=[n.id for n in ast.walk(fn) if isinstance(n,ast.Name)]
    assert all(x in names for x in ('PORTRAIT_BODY_ORDER','LEG_BODY_ORDER','DEFAULT_BODY_ORDER'))
    assert 'field.evaluate(points-total)' in value
    assert 'common_effective_order(check(state))' in source('leg_shape_project.py')
    assert 'common_effective_order(check(state))' in source('arm_shape_project.py')


def test_canonical_selection_decoder_reaches_every_output_bit_depth():
    runtime=source('people_engine_runtime.py');body=source('body_pose_render.py')
    assert 'body_source_path=None' in runtime
    assert 'source_path=body_source_path)' in runtime
    assert 'source_pixels=source)' not in runtime
    assert 'body_source_path=getattr(spec,\'body_pose_source_path\',None)' in source('people_export.py')
    assert 'from .prompted_mask_source import decode_source' in body
    assert "replay=decode_source(source_path,{k:frame[k] for k in ('sha256','width','height')},device='cpu')" in body


def test_proposal_start_preserves_other_capture_lifetimes():
    value=source('arm_shape_commands.py')
    proposal=value.split("if action=='proposal_start':",1)[1].split("if action!='execute':",1)[0]
    assert '_cancel_snapshot' not in proposal and '_close_owned_previews' not in proposal
    assert 'inspection.worker_running' in proposal and 'getattr(nested,\'job\',None)' in proposal


def test_durable_claim_and_verification_rejection_survive_lost_terminal_write():
    host=source('arm_shape_host.py');journal=source('arm_shape_receipts.py')
    assert "pending={'phase':'pending','request_id':request,'outcome_unknown':True}" in host
    assert "local['result'].get('publication_invalid')" in host
    assert "'publication_invalid':result.get('publication_invalid',False)" in host
    start=journal.index('os.replace(partial,target)')
    assert start<journal.index('self.entries[request_id]=',start)<journal.index('os.open(self.root',start)
    assert "meta=={'operation':operation,'digest':claim['digest']}" in source('body_pose_host.py')


def test_registered_transport_and_distribution_have_actual_consumers():
    server=source('server.py')
    assert '"arm_shape_protocol":1' in server and '"arm_shape"' in server
    assert 'def cmd_arm_shape' in source('arm_shape_registered_host.py')
    stage=(ROOT/'packaging/stage-engine.sh').read_text()
    assert 'build-arm-shape.sh' in stage and 'liblrt_arm_shape.so' in stage and 'sam2-LICENSE.txt' in stage
    native=(ROOT/'ui/src-tauri/src/main.rs').read_text()
    assert 'mod arm_shape_api;' in native and 'arm_shape_api::arm_shape' in native
    assert 'arm_shape:gesture:' in source('history_controller.py')
