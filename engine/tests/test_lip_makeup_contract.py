"""Authored but NOT executed in the development-only delivery.

Qoder should run these with the packaged Rust library and installed OpenCV.
Real-photo acceptance is separately required; fixtures are not product evidence.
"""
import numpy as np
import pytest
from lumaretouch_engine import lip_makeup_state as S
from lumaretouch_engine.lip_makeup_layer import LipMakeupLayer
from lumaretouch_engine.lip_makeup_native import propose


def test_signed_independent_recipe_and_strict_portability():
    r=S.patch(S.neutral(),{'brightness':.2,'dimensionality':-.3})
    assert S.patch(r,{'saturation':1})=={**r,'saturation':1}
    assert not S.active(None)
    for bad in ({}, {**r,'face_index':0}, {**r,'brightness':True}, {**r,'version':2}):
        with pytest.raises(ValueError): S.check(bad)


def test_zero_is_identity_without_loading_native_or_analyzing_geometry():
    pixels=np.full((20,20,3),.3,np.float32)
    layer=LipMakeupLayer((0,0,20,20),pixels,np.zeros((478,2)),None,backend='synthetic',identity='fixture')
    assert layer.solve(S.neutral()) is None
    assert np.array_equal(layer.source,pixels)
    with pytest.raises(ValueError,match='actual_selected_face_required'):
        layer.solve(S.patch(None,{'brightness':.2}))


def test_native_independence_and_measured_shading_only():
    lab=np.array([[[40.,20.,10.],[50.,20.,10.],[60.,20.,10.]]],np.float32)
    shading=np.array([[-4.,0.,4.]],np.float32)
    zero=propose(lab,shading,S.neutral())
    assert np.array_equal(zero,lab)
    sat=propose(lab,shading,S.patch(None,{'saturation':1}))
    assert np.array_equal(sat[...,0],lab[...,0])
    bright=propose(lab,shading,S.patch(None,{'brightness':1}))
    assert np.array_equal(bright[...,1:],lab[...,1:])
    dimensional=propose(lab,shading,S.patch(None,{'dimensionality':1}))
    assert dimensional[0,0,0]<lab[0,0,0] and dimensional[0,2,0]>lab[0,2,0]
    assert np.array_equal(dimensional[...,1:],lab[...,1:])
    assert np.array_equal(propose(lab,np.zeros_like(shading),S.patch(None,{'dimensionality':1})),lab)


def test_frozen_contribution_and_exact_tiles_preserve_upstream(monkeypatch):
    from types import SimpleNamespace
    import torch
    from lumaretouch_engine import lip_makeup_layer as L
    pixels=np.full((48,80,3),.4,np.float32)
    pixels[...,0]=.55
    pixels[...,1]+=.03*np.sin(np.arange(80,dtype=np.float32)[None,:]/7)
    support=np.zeros((48,80),np.float32); support[15:32,20:60]=1
    # Isolated composition fixture, NOT anatomical or portrait evidence.
    monkeypatch.setattr(L,'geometry',lambda *a,**kw:(support,{'geom_px':680,'gated_px':680,'reason':None},40.))
    layer=L.LipMakeupLayer((0,0,48,80),pixels,np.zeros((478,2)),None,backend='mediapipe',identity='fixture')
    original=layer.source.copy(); recipe=S.patch(None,{'brightness':.2,'dimensionality':.5})
    delta=layer.solve(recipe).copy()
    assert np.array_equal(original,layer.source)
    assert not np.any(delta[support==0])
    assert np.max(np.abs(delta))<=.18
    assert layer.solve(S.neutral()) is None
    assert np.array_equal(delta,layer.solve(recipe))
    incoming=torch.from_numpy(pixels*.85).permute(2,0,1)[None]
    whole=SimpleNamespace(h=48,w=80,device='cpu')
    L.attach_delta(whole,layer.window,delta)
    full=L.apply_delta(whole,incoming)
    assert torch.equal(full,(incoming+torch.from_numpy(delta).permute(2,0,1)[None]).clamp(0,1))
    stitched=torch.empty_like(full)
    for left,right in ((0,27),(27,53),(53,80)):
        tile=SimpleNamespace(h=48,w=right-left,device='cpu')
        L.attach_delta(tile,layer.window,delta,origin=(0,left))
        stitched[:,:,:,left:right]=L.apply_delta(tile,incoming[:,:,:,left:right])
    assert torch.equal(full,stitched)
    assert torch.equal(full[:,:,:15],incoming[:,:,:15])


def _ring_fixture(opening):
    from lumaretouch_engine.lip_makeup_geometry import OUTER,INNER
    lm=np.full((478,2),[80,45],dtype=np.float32)
    theta=np.linspace(-np.pi,np.pi,20,endpoint=False)
    lm[list(OUTER)]=np.stack((80+40*np.cos(theta),60+14*np.sin(theta)),axis=1)
    lm[list(INNER)]=np.stack((80+32*np.cos(theta),60+opening*np.sin(theta)),axis=1)
    lm[33],lm[133],lm[263],lm[362]=[45,25],[65,25],[115,25],[95,25]
    rgb=np.zeros((100,160,3),np.float32); rgb[:]=[.55,.18,.25]
    return lm,rgb


@pytest.mark.parametrize('opening',[0.,6.])
def test_ring_excludes_open_or_closed_cavity_and_exterior(opening):
    from lumaretouch_engine.lip_makeup_geometry import geometry
    lm,rgb=_ring_fixture(opening)
    mask,facts,width=geometry(lm,(100,160),rgb,np.zeros((100,160),np.float32),backend='mediapipe')
    # Topology-only synthetic fixture. Product still requires real detection.
    assert facts['reason'] is None and width==80
    assert np.count_nonzero(mask)>20
    assert mask[60,80]==0 and mask[40,80]==0 and mask[60,20]==0
    assert not np.any(mask[:45]) and not np.any(mask[75:])


def test_known_occluder_and_degenerate_inner_never_become_box_fills():
    from lumaretouch_engine.lip_makeup_geometry import geometry,INNER
    lm,rgb=_ring_fixture(6.)
    mask,facts,_=geometry(lm,(100,160),rgb,np.ones((100,160),np.float32),backend='mediapipe')
    assert not np.any(mask) and facts['reason']=='occluded_or_insufficient_support'
    lm[list(INNER)]=[80,60]
    mask,facts,_=geometry(lm,(100,160),rgb,np.zeros((100,160),np.float32),backend='mediapipe')
    assert not np.any(mask) and facts['reason']=='clipped_or_degenerate_lips'


def test_nested_project_corruption_is_not_silently_neutral():
    from lumaretouch_engine.lip_makeup_project import validate_records
    validate_records({'versions':[{'state':{'_lip_makeup':S.neutral()}}]})
    validate_records({'versions':[{'state':{}}]})  # legacy absence
    with pytest.raises(ValueError):
        validate_records({'history':{'undo':[{'_lip_makeup':None}]}})


def test_control_edits_merge_with_current_recipe_and_stale_document_rejects(monkeypatch):
    from types import SimpleNamespace
    from lumaretouch_engine import lip_makeup_command as C
    engine=SimpleNamespace(_load_id='current',_lip_makeup=S.patch(None,{'brightness':.6}),
        _vram=SimpleNamespace(),_guard_editable=lambda _:None,
        _write_current_frame=lambda _: {},doc_state=lambda: {})
    monkeypatch.setattr(C.R,'sync',lambda *a,**k:None)
    message={'cmd':'lip_makeup','document_id':'current','control':'saturation',
             'recipe':S.patch(None,{'saturation':.4})}
    C.apply(engine,message,lambda _:None)
    assert engine._lip_makeup['brightness']==.6 and engine._lip_makeup['saturation']==.4
    before=engine._lip_makeup.copy()
    with pytest.raises(ValueError,match='照片已切换'):
        C.apply(engine,{**message,'document_id':'previous'},lambda _:None)
    assert engine._lip_makeup==before


def test_export_tile_never_reanalyzes_proxy_source(monkeypatch):
    from types import SimpleNamespace
    from lumaretouch_engine import lip_makeup_runtime as R
    recipe=S.patch(None,{'brightness':.2})
    layer=SimpleNamespace(key=tuple(recipe[k] for k in S.KEYS),window=(0,0,2,2),
        delta=np.ones((2,2,3),np.float32)*.01,facts={})
    pipe=SimpleNamespace(h=2,w=2,device='cpu')
    R.install_export_tile(pipe,layer,(0,0),recipe)
    monkeypatch.setattr(R,'solve_preview',lambda *a: pytest.fail('tile re-solve'))
    R.refresh_source(pipe)
    assert pipe.lip_makeup_delta is not None
