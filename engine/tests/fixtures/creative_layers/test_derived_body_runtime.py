"""AUTHORED / UNRUN: body forwarding contracts, not native or visual acceptance."""
from types import SimpleNamespace
import numpy as np
import pytest
from test_derived_effects_contract import fixture
from lumaretouch_engine import body_pose_state as B, body_pose_render as BODY
from lumaretouch_engine import people_engine_runtime as R, people_owned_inputs as I
from lumaretouch_engine import arm_shape_project as P


def test_owned_preview_forwards_checked_body_without_original_path(monkeypatch):
    engine,state,_,source,_=fixture(monkeypatch)
    result=I.preview(engine,state)
    assert result['body_bank']==B.empty() and result['body_source']==source
    assert result['body_source_pixels'] is None and 'body_source_path' not in result
    with pytest.raises(ValueError):I.preview(engine,state,body_source={**source,'sha256':'a'*64})


def test_preview_joint_owner_receives_immutable_packet_not_display_pixels(monkeypatch):
    import torch
    engine,state,_,source,rgb=fixture(monkeypatch)
    pipe=SimpleNamespace(src_f32=torch.from_numpy(rgb.copy()).permute(2,0,1)[None].float()/255.,repair_base=None,repair_ops=[],redo_ops=[])
    from lumaretouch_engine.creative_derived_repair_runtime import bind
    engine._vram=pipe;bind(engine)
    packet=object();calls=[]
    monkeypatch.setattr(R,'prepare',lambda *a,**k:'face-prepared')
    monkeypatch.setattr(R,'body_budget',lambda *a:500_000_000)
    def prepare(*args,**kwargs):calls.append((args,kwargs));return 'joint-prepared'
    monkeypatch.setattr(BODY,'prepare',prepare)
    assert R.prepare_preview(pipe,state,source['sha256'],{},byte_budget=500_000_000,
        creative_source=source,creative_proxy=rgb,body_bank=B.empty(),body_source=source,
        body_source_pixels=packet)=='joint-prepared'
    assert calls[0][0][0]=='face-prepared' and calls[0][1]['source_pixels'] is packet
    assert calls[0][1]['source_path'] is None
    with pytest.raises(ValueError):R.prepare_preview(pipe,state,source['sha256'],{},byte_budget=500_000_000,
        creative_source=source,creative_proxy=rgb,body_source_path='/original.jpg')


def test_export_joint_owner_gets_exact_full_float_source(monkeypatch):
    _,state,_,source,_=fixture(monkeypatch)
    pixels=np.full((4,4,3),.123456,np.float32);calls=[]
    snapshot={'state':state,'asset_sha256':source['sha256'],'creative_source':source,'analyses':{}}
    frozen=P.snapshot(B.empty(),BODY.source(source))
    monkeypatch.setattr(R,'prepare',lambda *a,**k:'face-prepared')
    monkeypatch.setattr(R,'body_budget',lambda *a:500_000_000)
    def prepare(*args,**kwargs):calls.append((args,kwargs));return 'joint-prepared'
    monkeypatch.setattr(BODY,'prepare',prepare)
    assert R.prepare_export(snapshot,pixels,None,byte_budget=500_000_000,body_pose=frozen)=='joint-prepared'
    assert calls[0][1]['source_pixels'] is pixels and calls[0][1]['source_path'] is None
    assert pixels.dtype==np.float32 and pixels[0,0,0]==np.float32(.123456)
    with pytest.raises(ValueError):R.prepare_export(snapshot,pixels,None,byte_budget=500_000_000,
        body_pose=frozen,body_source_path='/original.jpg')
