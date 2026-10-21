"""TPS limits temporary pair matrices without lowering final field precision."""
import numpy as np
import pytest
from lumaretouch_engine.ops import deform as D


def test_large_tps_evaluation_caps_pairs_and_preserves_float32_field(monkeypatch):
    torch=pytest.importorskip('torch')
    P,delta,_=D.controls(D.analytic_frontal_landmarks(),'slim_face',1.0,512,512)
    P=torch.as_tensor(P,dtype=torch.float64)
    delta=torch.as_tensor(delta,dtype=torch.float64)
    state=D.tps_solve(P,delta,scale=512.)
    # Enough samples to require multiple blocks, including an irregular tail.
    points=torch.arange(65537,dtype=torch.float64)
    X=torch.stack((points.remainder(512),torch.floor(points/512)),dim=1)
    Xs=X/state['scale']
    kernel=D._u_kernel(torch.cdist(Xs,state['P']).pow(2))
    want=(kernel@state['sol']+state['aff'][0]+Xs@state['aff'][1:])*state['scale']
    calls=[]
    real=D._u_kernel
    def observed(a):
        calls.append(a.numel())
        return real(a)
    monkeypatch.setattr(D,'_u_kernel',observed)
    got=D.tps_eval(state,X)
    assert len(calls)>1
    assert max(calls)<=2_000_000
    assert got.dtype==torch.float64
    assert torch.equal(got.float(),want.float())
    assert float((got-want).abs().max())<1e-8
