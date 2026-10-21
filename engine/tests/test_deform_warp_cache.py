"""Geometry cache never caches edited pixels; all dependencies invalidate it."""
import numpy as np
import pytest
from lumaretouch_engine import vram as V
from lumaretouch_engine.ops.deform import analytic_frontal_landmarks


def pipe():
    torch = pytest.importorskip('torch')
    rgb = np.random.default_rng(101).integers(0,256,(96,80,3),dtype=np.uint8)
    p = V.make_pipeline('cpu',80,96,rgb)
    p.build_deform(analytic_frontal_landmarks())
    p.set_deform_amounts({'slim_face':0.6,'big_eye':0.3})
    return torch,p


def reference(torch,p,image):
    delta=None
    for kind,unit in p.deform_units.items():
        amount=p.deform_amounts.get(kind,0.0)
        if amount:
            delta=unit*amount if delta is None else delta+unit*amount
    grid=p.deform_grid_base-delta*torch.tensor([2/p.w,2/p.h],dtype=delta.dtype)
    result=torch.nn.functional.grid_sample(image,grid.to(image.dtype),mode='bilinear',padding_mode='border',align_corners=False)
    return torch.where((delta==0).all(dim=-1)[None],image,result)


def test_cache_reuses_geometry_not_image_and_invalidates_amounts(monkeypatch):
    torch,p=pipe()
    calls=[]
    real=V.prepare_warp_t
    def prepare(*args,**kwargs):
        calls.append(1)
        return real(*args,**kwargs)
    monkeypatch.setattr(V,'prepare_warp_t',prepare)
    for image in (p.src_f32,1-p.src_f32,p.src_f32*0.7):
        assert torch.equal(p.apply_deform(image),reference(torch,p,image))
    assert len(calls)==1
    p.set_deform_amounts({'slim_face':0.6})
    p.apply_deform(p.src_f32)
    assert len(calls)==1
    cache=p._deform_warp
    with pytest.raises(ValueError):p.set_deform_amounts({'slim_face':999})
    assert p._deform_warp is cache
    p.set_deform_amounts({'slim_face':0.4})
    assert p._deform_warp is None
    assert torch.equal(p.apply_deform(p.src_f32),reference(torch,p,p.src_f32))
    assert len(calls)==2


def test_rebuilt_and_adopted_fields_invalidate_and_cache_memory_is_counted():
    torch,p=pipe()
    before=p.deform_resident_bytes()
    p.apply_deform(p.src_f32)
    extra=sum(t.numel()*t.element_size() for t in p._deform_warp)
    assert p.deform_resident_bytes()==before+extra
    lm=analytic_frontal_landmarks().copy();lm[:,0]+=0.02
    p.build_deform(lm)
    assert p._deform_warp is None
    assert torch.equal(p.apply_deform(p.src_f32),reference(torch,p,p.src_f32))
    p.adopt_deform_field(torch.ones((1,p.h,p.w,2),dtype=torch.float32)*0.25)
    assert p._deform_warp is None
    assert torch.equal(p.apply_deform(p.src_f32),reference(torch,p,p.src_f32))
    p.clear_deform()
    assert p._deform_warp is None and p.deform_resident_bytes()==0
