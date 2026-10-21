"""Versioned linear-sRGB Y curves: Rust reference, parity and shared recipe paths."""
import copy
import json
import subprocess
import numpy as np
import pytest
from lumaretouch_engine.ops import curves as C


def recipe(points=None):
    value=C.default_curves();value.update(version=2,luminance_space=C.LUMINANCE_SPACE,
        luminance=points or [[0.,0.],[1.,1.]])
    return value


def rust_reference(image,points):
    request='luminance '+str(len(points))+' '+' '.join(str(x) for p in points for x in p)
    request+=' '+' '.join(str(float(x)) for x in image.reshape(-1))
    result=subprocess.run([str(C._compiler_path())],input=request,text=True,capture_output=True,timeout=3,check=True)
    return np.asarray(json.loads(result.stdout)).reshape(image.shape)


def test_legacy_recipe_is_unchanged_and_neutral_v2_has_exact_bypass():
    image=np.array([[[-0.,-.3,2.],[.2,.5,.8]]],np.float32)
    assert C.curves_np(image,recipe()) is image
    old=C.default_curves();old['red']=[[0,.1],[1,.9]]
    new=recipe();new['red']=copy.deepcopy(old['red'])
    assert np.array_equal(C.curves_np(image,old),C.curves_np(image,new))
    assert C.check_curves(old)==old and C.check_curves(old)['version']==1


def test_v2_domain_and_complete_channel_schema_are_required():
    for change in [{'luminance_space':'lab-l'},{'version':3},{'luminance':[[0,0],[0,.4],[1,1]]}]:
        bad=recipe();bad.update(change)
        with pytest.raises(ValueError):C.check_curves(bad)
    for key in ['luminance_space','luminance']:
        bad=recipe();del bad[key]
        with pytest.raises(ValueError):C.check_curves(bad)
    old=C.default_curves();old['luminance']=[[0,0],[1,1]]
    with pytest.raises(ValueError):C.check_curves(old)


def test_luminance_matches_rust_on_black_colour_negative_and_hdr():
    points=[[0,.08],[.3,.5],[1,.95]]
    image=np.array([[0,0,0],[1e-9,2e-9,0],[.2,.5,.8],[-.2,-.1,-.3],[1.3,.7,2.]],np.float32)
    actual=C.curves_np(image,recipe(points));expected=rust_reference(image,points)
    assert np.isfinite(actual).all() and actual.dtype==image.dtype
    assert np.max(np.abs(actual-expected))<3e-6
    assert actual[0,0]==actual[0,1]==actual[0,2]


def test_luminance_is_not_an_rgb_master_curve():
    points=[[0,.1],[1,.9]];image=np.array([[.2,.5,.8]],np.float32)
    master=C.default_curves();master['master']=points
    assert not np.allclose(C.curves_np(image,master),C.curves_np(image,recipe(points)))


def test_torch_cpu_matches_numpy_for_v2_and_disabled_identity():
    torch=pytest.importorskip('torch')
    spec=recipe([[0,.05],[.5,.7],[1,.95]])
    image=np.random.default_rng(9).uniform(-.15,1.2,(13,17,3)).astype(np.float32)
    tensor=torch.from_numpy(image.transpose(2,0,1)[None].copy())
    actual=C.curves_t(tensor,C.tensor_bundles(spec,'cpu',torch.float32)).numpy()[0].transpose(1,2,0)
    assert np.max(np.abs(actual-C.curves_np(image,spec)))<1e-5
    spec['enabled']=False
    assert C.curves_t(tensor,C.tensor_bundles(spec,'cpu',torch.float32)) is tensor


def test_v2_survives_history_scope_and_shared_export_snapshot():
    from lumaretouch_engine.server import Engine
    from lumaretouch_engine import scope as S
    from lumaretouch_engine.export_recipe import build_export_spec
    from test_export_per_image_recipe import _batch_snap
    e=Engine('luminance-state');state=e._capture_state();spec=recipe([[0,.1],[1,.9]])
    changed=S.apply_modules(state,{S.OP_CURVES:{'recipe':spec}});e._apply_state(changed)
    assert e._curves==spec and not C.is_identity(e._curves)
    assert 'RGB/master 曲线（含亮度通道）' in e._master16_blockers(scale=1,sharpen=0)
    assert e._history_capture()['_curves']==spec
    snap=_batch_snap();snap['curves']=spec;snap['strength']=0
    output,skipped=build_export_spec(snap,64,64,for_document=True)
    assert output.curves==spec and skipped==[]


def test_luminance_export16_uses_shared_float_pipeline():
    pytest.importorskip('torch')
    from lumaretouch_engine.export import export_image16,ExportSpec
    source=np.broadcast_to(np.linspace(0,65535,513,dtype=np.uint16)[None,:,None],(64,513,3)).copy()
    spec=recipe([[0,.03],[.4,.55],[1,.97]])
    expected=np.rint(np.clip(C.curves_np(source.astype(np.float32)/65535,spec),0,1)*65535).astype(np.uint16)
    actual,_=export_image16(source,ExportSpec(strength=0,curves=spec),device='cpu',tile=256)
    assert np.max(np.abs(actual.astype(np.int32)-expected.astype(np.int32)))<=2
    assert len(np.unique(actual[0,:,0]))>256


def boundary_vectors():
    # Construct in linear space so opposing channels deliberately nearly cancel Y.
    w=np.asarray(C.Y_WEIGHTS);rows=[]
    for target_y in [-1.01e-7,-1e-7,-.99e-7,0.,.99e-7,1e-7,1.01e-7]:
        rows.append([.2,(target_y-w[0]*.2)/w[1],0.])
    for red in [-1e-8,0.,1e-8]:rows.append([red,.2,.1])
    linear=np.asarray(rows,np.float32)
    a=np.abs(linear)
    rgb=(np.sign(linear)*np.where(a<=.0031308,12.92*a,1.055*a**(1/2.4)-.055)).astype(np.float32)
    return rgb, [[0,.1],[1,.9]]


def test_near_zero_and_mixed_sign_vectors_remain_continuous_and_match_rust():
    rgb,points=boundary_vectors();actual=C.curves_np(rgb,recipe(points))
    assert np.isfinite(actual).all()
    assert np.max(np.abs(actual-rust_reference(rgb,points)))<4e-6
    assert np.max(np.abs(np.diff(actual[:7],axis=0)))<1e-5
    assert np.max(np.abs(np.diff(actual[7:],axis=0)))<1e-5


def test_near_zero_tensor_vectors_match_numpy():
    torch=pytest.importorskip('torch')
    rgb,points=boundary_vectors();actual=C.curves_np(rgb,recipe(points))
    tensor=torch.from_numpy(rgb.T[None,:,None,:].copy())
    tensor_result=C.curves_t(tensor,C.tensor_bundles(recipe(points),'cpu',torch.float32)).numpy()[0,:,0,:].T
    assert np.max(np.abs(actual-tensor_result))<1e-5
