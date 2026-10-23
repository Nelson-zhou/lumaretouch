"""AUTHORED / UNRUN: normalized deterministic heal, not visual acceptance."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine.ops import heal_vector as H,clone_stamp as C,inpaint as I
from lumaretouch_engine import heal_vector_geometry as G,creative_derived_repairs as D
from lumaretouch_engine.repair_record import DEFAULT_REPAIR,RepairOp,check_repair_params
from lumaretouch_engine.color_action_sampling import Projection


def recipe(opacity=1.):
    return {'version':H.VERSION,'points':[[.4,.5],[.6,.5]],'axes':[[.06,0],[0,.06]],
        'hardness':.5,'opacity':opacity,'reference_size':[64,64],'solver':deepcopy(DEFAULT_REPAIR)}


def test_recipe_exact_domain_and_solver_contract():
    p=recipe();assert check_repair_params('heal_vector',p)==p
    for bad in ({**p,'offset':[0,0]},{**p,'reference_size':[True,64]},
                {**p,'version':'heal'},{**p,'solver':{'pad':32}}):
        with pytest.raises(ValueError):H.check_recipe(bad)
    other=H.check_recipe(p);other['points'][0][0]=.2
    assert p['points'][0][0]==.4


def test_context_pad_scales_without_changing_solver_defaults():
    p=recipe()
    assert H.raster_plan((64,64),p)[1]==32
    assert H.raster_plan((512,512),p)[1]==256
    assert H.raster_plan((32,32),p)[1]==16
    assert p['solver']==DEFAULT_REPAIR
    with pytest.raises(ValueError):H.raster_plan((12000,12000),p)


def test_inverse_uses_presented_geometry_and_rejects_padding(monkeypatch):
    from lumaretouch_engine import cpu_memory_budget as B
    monkeypatch.setattr(B,'available_estimate',lambda:2_000_000_000)
    spec=Projection(64,64,(0.,0.,1.,1.),0.,(0,0,64,64),(64,64))
    stroke={'points':[[.4,.5],[.6,.5]],'size':.12,'hardness':.5,'opacity':1.}
    valid=np.ones((64,64),bool)
    p,weight=G.inverse_stroke(spec,stroke,valid,[512,512])
    assert p['reference_size']==[64,64] and 'offset' not in p and 'source' not in p
    assert weight.shape==(64,64) and weight.dtype==np.uint8 and weight.any()
    valid[32,32]=False
    with pytest.raises(ValueError):G.inverse_stroke(spec,stroke,valid,[512,512])
    with pytest.raises(ValueError):G.inverse_stroke(spec,{**stroke,'source':[.5,.5]},np.ones((64,64),bool),[512,512])


def test_full_resolution_raster_does_not_scale_proxy_bitmap():
    p=recipe();small,_=C.raster((64,64),H._brush(p));full,_=C.raster((512,512),H._brush(p))
    assert full.dtype==small.dtype==np.float32
    assert full.shape[0]>small.shape[0] and full.shape[1]>small.shape[1]
    assert np.any((full>0)&(full<1))


def test_zero_opacity_is_exact_noop_without_solver(monkeypatch):
    import torch
    cur=torch.full((1,3,64,64),.500013,dtype=torch.float32)
    def forbidden(*a,**k):raise AssertionError('No-op invoked solver')
    monkeypatch.setattr(I,'inpaint_t',forbidden)
    result,box=H.apply_t(cur,recipe(0.))
    assert result is cur and box is None


def test_actual_float_replay_preserves_outside_and_solver_contract(monkeypatch):
    import torch
    from lumaretouch_engine import cpu_memory_budget as B
    monkeypatch.setattr(B,'available_estimate',lambda:2_000_000_000)
    cur=torch.full((1,3,256,256),.500013,dtype=torch.float32);seen=[]
    def solve(sub,weight,**kwargs):
        seen.append(kwargs);return sub+weight*.01
    monkeypatch.setattr(I,'inpaint_t',solve)
    p=recipe();out,box=H.apply_t(cur,p)
    assert seen[0]['smooth_iters']==1 and seen[0]['refine_iters']==6 and seen[0]['kappa']==.06
    assert torch.equal(cur,torch.full_like(cur,.500013))
    assert torch.equal(out[...,0,0],cur[...,0,0]) and not torch.equal(out,cur)
    monkeypatch.setattr(B,'available_estimate',lambda:1)
    with pytest.raises(ValueError,match='memory'):H.apply_t(cur,p)


def test_derived_kind_requires_source_and_old_heal_stays_fenced():
    source={'sha256':'a'*64,'width':64,'height':64}
    vector=RepairOp(1,np.ones((64,64),np.uint8),recipe(),'heal_vector',source)
    D.validate_source_ops([vector],source)
    with pytest.raises(ValueError):D.validate_source_ops([vector],None)
    legacy=RepairOp(2,np.ones((64,64),np.uint8),deepcopy(DEFAULT_REPAIR),'heal',source)
    with pytest.raises(ValueError):D.validate_source_ops([legacy],source)
