from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import color_action_sampling as S
from lumaretouch_engine import white_balance_pick_math as P
from lumaretouch_engine.ops import exposure as E, geometry as G

AVAILABLE=16*1024**3


def fixture(pixels,rect=(0,0,1,1),rotation=0):
    from lumaretouch_engine.vram import PreviewPipeline
    class Pipeline:
        w=int(pixels.shape[-1]);h=int(pixels.shape[-2]);crop_rect=rect;crop_rotation=rotation
        device=SimpleNamespace(type='cpu');calls=0
        repair_version=0;retouched=pixels;filter_key=(12,.0006,4,0.,0.,1.,0)
        _filter_parameters=staticmethod(PreviewPipeline._filter_parameters)
        def has_light(self):return False
        def has_deform(self):return False
        def retouch(self,strength,channel,render_stage,**params):
            assert render_stage=='wb-input' and strength==.25 and channel is None and params=={}
            self.calls+=1;return pixels
    pipe=Pipeline()
    return pipe,S.Projection.from_pipeline(pipe)


def test_rotation_budget_is_checked_before_any_render_or_allocation():
    pipe=SimpleNamespace(w=1_000_000,h=1,crop_rect=(0,0,1,1),crop_rotation=45)
    spec=S.Projection.from_pipeline(pipe)
    assert spec.rotated[0]*spec.rotated[1]>S.MAX_ROTATION_PIXELS
    with pytest.raises(ValueError,match='raster budget'):S.admit(spec,AVAILABLE)
    pipe.w=8;pipe.h=6;pipe.crop_rotation=0;pipe.device=SimpleNamespace(type='cpu')
    pipe.retouch=lambda *a,**k:pytest.fail('render must not start before admission')
    spec=S.Projection.from_pipeline(pipe)
    with pytest.raises(ValueError,match='available memory'):S.preview(pipe,spec,.25,None,{},available=1)


def test_descriptor_freezes_integer_crop_rotation_and_resize_contract():
    pipe=SimpleNamespace(w=11,h=7,crop_rect=(.1,.2,.9,.8),crop_rotation=90)
    spec=S.Projection.from_pipeline(pipe);d=spec.descriptor()
    assert d['integer_crop']==[1,1,10,6] and d['rotated']==[5,9] and d['target']==[11,7]
    assert d['resize']=='bilinear' and not d['align_corners'] and not d['antialias']
    d['rect'][0]=.8;assert spec.rect[0]==.1


def test_decode_precedes_projection_and_averaging():
    torch=pytest.importorskip('torch')
    pixels=torch.tensor([.1,.9,.2,.3],dtype=torch.float32).reshape(1,1,1,4).repeat(1,3,2,1)
    pipe,spec=fixture(pixels,rect=(0,0,.5,1));region={'x':1,'y':0,'width':2,'height':2}
    rows=S.sample(pipe,spec,.25,None,{},region,available=AVAILABLE)
    mean=np.mean(np.asarray(rows)[:,:3],axis=0)
    decoded=E._lin_np(np.array([.1,.9],dtype=np.float64))
    np.testing.assert_allclose(mean,np.full(3,decoded.mean()),rtol=0,atol=2e-7)
    wrong=E._lin_np(np.array([.5]))[0]
    assert abs(mean[0]-wrong)>.1
    assert all(row[3]==1 and row[4]==0 for row in rows)
    preview=S.preview(pipe,spec,.25,None,{},available=AVAILABLE)
    np.testing.assert_allclose(E._lin_t(preview)[0,:,0,1:3].mean(dim=1).numpy(),mean,atol=2e-7)


@pytest.mark.parametrize('rect,angle',[( (.125,.167,.875,.833),23.0),((0,0,1,1),90.0),((0,0,.125,1),60.0)])
def test_linear_projection_matches_independent_numpy_geometry_then_explicit_resize(rect,angle):
    torch=pytest.importorskip('torch');F=torch.nn.functional
    pixels=torch.linspace(.1,.9,3*6*8).reshape(1,3,6,8)
    pipe,spec=fixture(pixels,rect,angle)
    rows=S.sample(pipe,spec,.25,None,{}, {'x':0,'y':0,'width':8,'height':6},available=AVAILABLE)
    encoded=pixels[0].permute(1,2,0).numpy().astype(np.float64)
    expected=G.crop_rotate_np(E._lin_np(encoded),rect,angle,uint8=False)
    expected=F.interpolate(torch.from_numpy(expected).permute(2,0,1)[None],size=(6,8),mode='bilinear',align_corners=False)
    np.testing.assert_allclose(np.array(rows)[:,:3],expected[0].permute(1,2,0).reshape(-1,3).numpy(),atol=2e-6,rtol=0)


def test_one_clipped_source_contribution_cannot_hide_in_a_nonclipped_mean():
    torch=pytest.importorskip('torch')
    pixels=torch.tensor([1.,.3,.3,.3]).reshape(1,1,1,4).repeat(1,3,2,1)
    pipe,spec=fixture(pixels,rect=(0,0,.5,1))
    rows=S.sample(pipe,spec,.25,None,{}, {'x':1,'y':0,'width':1,'height':1},available=AVAILABLE)
    assert max(rows[0][:3])<1 and rows[0][4]>0
    with pytest.raises(ValueError,match='Clipped'):P.calculate(rows,(1,1,1))


def test_rotation_fill_is_rejected_by_coverage_not_colour():
    torch=pytest.importorskip('torch');pipe,spec=fixture(torch.full((1,3,6,8),.4),rotation=37)
    rows=S.sample(pipe,spec,.25,None,{}, {'x':0,'y':0,'width':8,'height':6},available=AVAILABLE)
    assert min(row[3] for row in rows)==0 and max(row[3] for row in rows)>.99
    with pytest.raises(ValueError,match='Coverage'):P.calculate(rows,(1,1,1))


def test_geometry_change_and_bad_stage_fail_before_sample_is_returned():
    torch=pytest.importorskip('torch');pipe,spec=fixture(torch.full((1,3,6,8),.4))
    pipe.crop_rotation=1
    with pytest.raises(ValueError,match='geometry changed'):S.preview(pipe,spec,.25,None,{},available=AVAILABLE)
    assert pipe.calls==0
    pipe.crop_rotation=0;pipe.retouch=lambda *a,**k:torch.full((1,3,6,8),float('nan'))
    with pytest.raises(ValueError,match='invalid encoded RGB'):S.preview(pipe,spec,.25,None,{},available=AVAILABLE)


def test_real_production_prefix_stops_before_exposure_and_preserves_upstream_order(monkeypatch):
    torch=pytest.importorskip('torch')
    from lumaretouch_engine.vram import PreviewPipeline
    pipe=PreviewPipeline('cpu',8,6);pipe.load_rgb_u8(np.full((6,8,3),100,np.uint8));seen=[]
    for name,delta in [('apply_deform',.01),('apply_enhance',.02)]:
        def apply(value,name=name,delta=delta):seen.append(name);return value+delta
        monkeypatch.setattr(pipe,name,apply)
    monkeypatch.setattr(pipe,'apply_exposure',lambda *a:pytest.fail('WB input must exclude the entire exposure stage'))
    out=pipe.retouch(0,render_stage='wb-input')
    assert seen==['apply_deform','apply_enhance']
    np.testing.assert_allclose(out.numpy(),100/255+.03,atol=1e-7)
    with pytest.raises(ValueError,match='render stage'):pipe.retouch(0,render_stage='invented')


def test_real_non_neutral_filter_overshoot_only_rejects_its_selected_contribution():
    torch=pytest.importorskip('torch')
    from lumaretouch_engine.vram import PreviewPipeline
    image=np.full((12,12,3),128,np.uint8)
    for y in range(4,8):
        for x in range(4,8):image[y,x]=255 if (x+y)%2==0 else 0
    pipe=PreviewPipeline('cpu',12,12);pipe.load_rgb_u8(image)
    params={'radius':1,'texture_radius':1,'detail_gain':2,'mid_gain':1,'broad_gain':1}
    stage=pipe.retouch(1,render_stage='wb-input',**params)
    assert stage.max().item()>1 and stage.min().item()<0
    spec=S.Projection.from_pipeline(pipe)
    preview=S.preview(pipe,spec,1,None,params,available=AVAILABLE)
    assert torch.isfinite(preview).all()
    safe=S.sample(pipe,spec,1,None,params,{'x':0,'y':0,'width':1,'height':1},available=AVAILABLE)
    assert P.calculate(safe,(1,1,1)).gains==pytest.approx((1,1,1))
    for x in (4,5):
        clipped=S.sample(pipe,spec,1,None,params,{'x':x,'y':4,'width':1,'height':1},available=AVAILABLE)
        with pytest.raises(ValueError,match='Clipped'):P.calculate(clipped,(1,1,1))


def test_cold_filter_and_light_cache_are_rejected_before_retouch():
    torch=pytest.importorskip('torch');pipe,spec=fixture(torch.full((1,3,6,8),.4))
    good=pipe.filter_key;pipe.filter_key=None
    with pytest.raises(ValueError,match='filter cache'):S.preview(pipe,spec,.25,None,{},available=AVAILABLE)
    assert pipe.calls==0
    pipe.filter_key=good;pipe.has_light=lambda:True
    pipe.light_version=1;pipe.light_exposure=1.;pipe.light_radius=1000
    pipe.light_src=None;pipe.light_src_key=None
    with pytest.raises(ValueError,match='source light cache'):S.preview(pipe,spec,0,None,{},available=AVAILABLE)
    assert pipe.calls==0


def test_shared_projection_keeps_ordinary_output_pixels_exactly(monkeypatch):
    torch=pytest.importorskip('torch');F=torch.nn.functional
    from lumaretouch_engine.vram import PreviewPipeline
    pipe=PreviewPipeline('cpu',8,6);pipe.load_rgb_u8(np.arange(6*8*3,dtype=np.uint8).reshape(6,8,3))
    pipe.set_geometry((.125,.167,.875,.833),23)
    image=torch.linspace(0,1,3*6*8).reshape(1,3,6,8)
    expected=G.crop_rotate_t(image.permute(0,2,3,1)[0],pipe.crop_rect,pipe.crop_rotation,uint8=False)
    if tuple(expected.shape[:2])!=(6,8):
        expected=F.interpolate(expected.permute(2,0,1)[None],size=(6,8),mode='bilinear',align_corners=False)[0].permute(1,2,0)
    expected=expected.permute(2,0,1).contiguous()[None]
    assert torch.equal(pipe.apply_geometry(image),expected)
    seen=[]
    for name in ('apply_deform','apply_enhance','apply_exposure','apply_levels','apply_curves','apply_hsl','apply_lut','apply_grade','apply_background','apply_geometry'):
        def apply(value,name=name):seen.append(name);return value
        monkeypatch.setattr(pipe,name,apply)
    pipe.retouch(0)
    assert seen==['apply_deform','apply_enhance','apply_exposure','apply_levels','apply_curves','apply_hsl','apply_lut','apply_grade','apply_background','apply_geometry']
