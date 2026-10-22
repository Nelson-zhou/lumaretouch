"""LumaRetouch integration guards; tests execute only in the designated test runner."""
import numpy as np
import pytest
pytest.importorskip('cv2')
from lumaretouch_engine.ops import source_patch as P


def recipe(polygon=None,offset=None):
    return {'version':P.VERSION,'polygon':polygon or [[.65,.35],[.85,.35],[.85,.65],[.65,.65]],
            'offset':[-.45,0] if offset is None else offset}


def image():
    rng=np.random.default_rng(123)
    rgb=np.broadcast_to(np.linspace(.3,.6,160,dtype=np.float32)[None,:,None],(100,160,3)).copy()
    rgb[:,:65]*=1+.04*rng.standard_normal((100,65,1)).astype(np.float32)
    rgb[43:57,112:128]=.1
    return rgb


def test_independent_source_texture_removes_defect_and_keeps_target_lighting():
    rgb=image();original=rgb.copy();out=P.apply(rgb,recipe())
    assert out.dtype==np.float32 and np.isfinite(out).all()
    assert out[45:55,115:125].mean()>.45 and out[45:55,115:125].std()>.003
    np.testing.assert_array_equal(rgb,original)
    np.testing.assert_array_equal(out[:,:65],rgb[:,:65])
    np.testing.assert_array_equal(out[:8],rgb[:8])


def test_zero_displacement_is_exact_and_owns_returned_array():
    rgb=image();out=P.apply(rgb,recipe(offset=[0,0]))
    np.testing.assert_array_equal(out,rgb);assert out is not rgb


@pytest.mark.parametrize('bad',[
    {'version':'unknown','polygon':[[.2,.2],[.3,.2],[.3,.3]],'offset':[.1,0]},
    {'version':P.VERSION,'polygon':[[True,.2],[.3,.2],[.3,.3]],'offset':[.1,0]},
    {'version':P.VERSION,'polygon':[[.2,float('nan')],[.3,.2],[.3,.3]],'offset':[.1,0]},
    {'version':P.VERSION,'polygon':[[.2,.2],[.3,.2]],'offset':[.1,0]},
    {'version':P.VERSION,'polygon':[[.2,.2],[.3,.2],[.3,.3]],'offset':[.9,0]},
])
def test_invalid_recipe_is_rejected_not_silently_healed(bad):
    with pytest.raises(ValueError):P.apply(image(),bad)


def test_context_touching_an_edge_is_not_the_upstream_silent_noop():
    rgb=np.full((100,160,3),.5,np.float32);rgb[45:55,18:28]=.1
    r=recipe([[.10,.4],[.20,.4],[.20,.6],[.10,.6]],[.75,0])
    out=P.apply(rgb,r)
    assert out[47:53,20:26].mean()>.4
    np.testing.assert_array_equal(out[:,100:],rgb[:,100:])


def test_rasterized_source_outside_or_missing_lighting_context_rejects():
    rgb=np.full((20,20,3),.4,np.float32)
    r=recipe([[0,0],[.5,0],[.5,1],[0,1]],[.5,0])
    with pytest.raises(ValueError):P.apply(rgb,r)


def test_sub_eight_bit_source_texture_survives_float_processing():
    first=np.full((100,160,3),.4,np.float32);second=first.copy()
    y,x=np.mgrid[:100,:65]
    second[:,:65]+=(((x+y)%2)*2-1)[...,None].astype(np.float32)/65535
    first[43:57,112:128]=second[43:57,112:128]=.1
    a=P.apply(first,recipe())[45:55,115:125];b=P.apply(second,recipe())[45:55,115:125]
    assert np.max(np.abs(a-b))>1e-6
    assert np.any(np.rint(a*65535)!=np.rint(b*65535))
    np.testing.assert_array_equal(np.rint(a*255),np.rint(b*255))


def test_selection_raster_is_local_not_a_full_source_mask(monkeypatch):
    rgb=np.full((500,1000,3),.4,np.float32);calls=[];original=P.selection_mask
    def tracked(shape,polygon,box=None):
        assert box is not None
        calls.append((box[1]-box[0])*(box[3]-box[2]));return original(shape,polygon,box)
    monkeypatch.setattr(P,'selection_mask',tracked)
    P.apply(rgb,recipe([[.6,.4],[.62,.4],[.62,.44],[.6,.44]],[-.3,0]))
    assert calls and max(calls)<10000


def test_oversized_selection_is_rejected_before_raster_allocation(monkeypatch):
    # Zero-stride read-only view; no huge backing allocation is necessary.
    rgb=np.lib.stride_tricks.as_strided(np.zeros(1,np.float32),shape=(4001,4001,3),strides=(0,0,0),writeable=False)
    monkeypatch.setattr(P.cv2,'fillPoly',lambda *a,**k:pytest.fail('allocation guard was bypassed'))
    with pytest.raises(ValueError,match='raster budget'):P.apply(rgb,recipe([[0,0],[1,0],[1,1],[0,1]],[0,0]))


def test_local_and_full_mask_rasterization_share_the_global_fixed_point_lattice():
    polygon=[[.3011,.3017],[.6002,.3009],[.6008,.7001],[.3002,.6999]]
    full=P.selection_mask((100,160),polygon)
    local=P.selection_mask((100,160),polygon,(20,80,40,110))
    np.testing.assert_array_equal(local,full[20:80,40:110])


def test_missing_target_lighting_context_is_explicit():
    rgb=np.full((20,20,3),.4,np.float32)
    r=recipe([[0,0],[.9,0],[.9,1],[0,1]],[.05,0])
    with pytest.raises(ValueError,match='surrounding target pixels'):P.apply(rgb,r)


def test_zero_offset_does_not_accept_nonfinite_selected_pixels():
    rgb=image();rgb[50,120]=np.nan
    with pytest.raises(ValueError,match='nonfinite'):P.apply(rgb,recipe(offset=[0,0]))
