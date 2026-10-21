"""True RGB16 editing must not pass through an 8-bit framebuffer."""
import numpy as np
import pytest
from lumaretouch_engine import export as ex


def gradient(h=256,w=256):
    a=np.arange(h*w,dtype=np.uint32).reshape(h,w)
    return np.stack([(a*5+3)%65536,(a*7+11)%65536,(a*13+17)%65536],axis=-1).astype(np.uint16)


def test_neutral_rgb16_edit_pipeline_is_exact_and_keeps_low_bits():
    pytest.importorskip('torch')
    a=gradient()
    got,info=ex.export_image16(a,ex.ExportSpec(strength=0),device='cpu',tile=256)
    np.testing.assert_array_equal(got,a)
    assert got.dtype==np.uint16
    assert np.unique(got[...,0]).size==65536
    assert info['bits']==16


def test_rgb16_exposure_uses_same_float_operator_without_uint8_pack(monkeypatch):
    pytest.importorskip('torch')
    from lumaretouch_engine.vram import PreviewPipeline
    a=gradient(73,89)
    spec=ex.ExportSpec(strength=0,exposure=(.37,0,0,0,0,0,0))
    pipe=PreviewPipeline('cpu',89,73);pipe.load_rgb_f32(a.astype(np.float32)/65535)
    pipe.set_exposure(.37,0,0)
    expected=np.clip(np.rint(pipe.retouch(0)[0].permute(1,2,0).numpy().astype(np.float64)*65535),0,65535).astype(np.uint16)
    def forbidden(*a,**k):raise AssertionError('16-bit export used uint8 framebuffer')
    monkeypatch.setattr(PreviewPipeline,'pack',forbidden)
    got,info=ex.export_image16(a,spec,device='cpu',tile=256)
    np.testing.assert_array_equal(got,expected)
    assert np.count_nonzero(got!=a)>0 and np.unique(got[...,0]).size>256


def test_rgb16_filtered_tiles_match_same_chain_whole_frame():
    pytest.importorskip('torch')
    a=gradient(300,330)
    spec=ex.ExportSpec(strength=.35,radius=3,texture_radius=2,detail_gain=.85,mid_gain=.1,broad_gain=.05)
    tiled,_=ex.export_image16(a,spec,device='cpu',tile=256)
    whole,_=ex.export_image16(a,spec,device='cpu',tile=512)
    assert np.abs(tiled.astype(np.int32)-whole.astype(np.int32)).max()<=1


def test_rgb16_resample_and_sharpen_retain_more_than_8bit_levels():
    pytest.importorskip('torch')
    a=gradient(70,90)
    spec=ex.ExportSpec(strength=0,scale=2,sharpen_amount=.2,sharpen_radius=1,sharpen_threshold=0)
    got,_=ex.export_image16(a,spec,device='cpu',tile=256)
    assert got.shape==(140,180,3) and got.dtype==np.uint16
    assert min(np.unique(got[...,c]).size for c in range(3))>256


def test_rgb16_api_does_not_promote_uint8_source_as_true_16bit():
    with pytest.raises(ex.ExportError,match='uint16'):
        ex.export_image16(np.zeros((20,30,3),np.uint8),ex.ExportSpec(strength=0),device='cpu')


def test_rgb16_repair_and_skin_combine_like_live_float_chain():
    pytest.importorskip('torch')
    from lumaretouch_engine.vram import PreviewPipeline,RepairOp
    from lumaretouch_engine.quant import quantize16_np
    a=gradient(120,160)
    weight=np.zeros((120,160),np.uint8);weight[50:60,70:80]=255
    repair=[RepairOp(1,weight)]
    masks=np.zeros((1,120,160),np.float32);masks[:,20:100,20:140]=.75
    spec=ex.ExportSpec(strength=.4,radius=3,texture_radius=2,repair=repair,
                      channel='skin',masks=masks,mask_names=['skin'],landmarks=np.zeros((478,3),np.float32))
    got,info=ex.export_image16(a,spec,device='cpu',tile=256)
    pipe=PreviewPipeline('cpu',160,120);pipe.load_rgb_f32(a.astype(np.float32)/65535)
    pipe.set_repair_ops(repair)
    carrier=ex._MaskCarrier(masks,spec.landmarks);carrier._carrier_names=['skin'];pipe.load_face(carrier)
    result=pipe.retouch(.4,radius=3,texture_radius=2,channel='skin')
    expected=quantize16_np(result[0].permute(1,2,0).numpy())
    np.testing.assert_array_equal(got,expected)
    assert info['applied']==1 and np.any(got!=a)
    repaired,_=ex.apply_repair_full(a,repair,'cpu')
    np.testing.assert_array_equal(got[masks[0]==0],quantize16_np(repaired)[masks[0]==0])


def test_rgb16_pointwise_color_chain_is_exact_across_tiles():
    pytest.importorskip('torch')
    from lumaretouch_engine.ops.lut import bake
    a=gradient(270,310)
    spec=ex.ExportSpec(strength=0,exposure=(.15,100,0,0,0,0,0),
                      cube=bake(lambda x:np.clip(x*.9+.025,0,1),17),grade=(.005,-.07,.03,1))
    tiled,_=ex.export_image16(a,spec,device='cpu',tile=256)
    whole,_=ex.export_image16(a,spec,device='cpu',tile=512)
    np.testing.assert_array_equal(tiled,whole)
    assert np.any(tiled!=a)


def test_rgb16_upscale_sharpen_has_no_tile_seams():
    pytest.importorskip('torch')
    a=gradient(270,280)
    spec=ex.ExportSpec(strength=0,scale=2,sharpen_amount=.2,sharpen_radius=1,sharpen_threshold=0)
    tiled,_=ex.export_image16(a,spec,device='cpu',tile=256)
    whole,_=ex.export_image16(a,spec,device='cpu',tile=512)
    np.testing.assert_array_equal(tiled,whole)


def test_rgb16_crop_rotation_happens_before_final_quantization(monkeypatch):
    pytest.importorskip('torch')
    from lumaretouch_engine.ops import geometry
    a=gradient(50,70)
    original=geometry.crop_rotate_np;seen=[]
    def checked(pixels,*args,**kwargs):
        seen.append(pixels.dtype)
        assert pixels.dtype.kind=='f'
        return original(pixels,*args,**kwargs)
    monkeypatch.setattr(geometry,'crop_rotate_np',checked)
    got,info=ex.export_image16(a,ex.ExportSpec(strength=0),device='cpu',crop_rect=(.1,.1,.9,.9),rotation_degrees=90)
    np.testing.assert_array_equal(got,np.rot90(a[5:45,7:63],-1))
    assert seen and info['crop_applied'] and (info['h'],info['w'])==got.shape[:2]


def test_rgb16_deformation_is_consistent_across_tiles():
    pytest.importorskip('torch')
    from lumaretouch_engine.ops.deform import analytic_frontal_landmarks
    a=gradient(300,330)
    spec=ex.ExportSpec(strength=.25,radius=3,texture_radius=2,
                      deform_amounts={'slim_face':.4},landmarks=analytic_frontal_landmarks())
    tiled,_=ex.export_image16(a,spec,device='cpu',tile=256)
    whole,_=ex.export_image16(a,spec,device='cpu',tile=512)
    error=np.abs(tiled.astype(np.int32)-whole.astype(np.int32))
    assert error.max()<=1, (int(error.max()),float(error.mean()))
    assert np.any(tiled!=a)


@pytest.mark.parametrize('profile',['source','srgb'])
def test_edited_rgb16_file_uses_real_icc_conversion_and_readback(tmp_path,profile):
    pytest.importorskip('torch')
    import tifffile
    from lumaretouch_engine.decode import load_full
    from lumaretouch_engine.color16 import convert_rgb16
    from test_color16 import linear_srgb_profile
    a=gradient(64,80);icc=linear_srgb_profile();src=tmp_path/'linear.tif'
    tifffile.imwrite(src,a,photometric='rgb',extratags=[(34675,'B',len(icc),icc,False)])
    decoded=load_full(str(src),want_bits=16)
    spec=ex.ExportSpec(strength=0,exposure=(.23,0,0,0,0,0,0))
    path=tmp_path/'edited.tif'
    info=ex.export_edited_16bit(decoded,spec,str(path),device='cpu',output_profile=profile,tiff_compression='deflate')
    working=ex._srgb_bytes()
    expected,_=ex.export_image16(convert_rgb16(a,icc,working),spec,device='cpu')
    target=icc if profile=='source' else working
    expected=convert_rgb16(expected,working,target)
    np.testing.assert_array_equal(ex.read_tiff16(str(path)),expected)
    assert ex.read_tiff16_icc(str(path))==target
    assert info['readback_max_diff']==0 and info['icc_readback_matches']
    assert info['pipeline']=='float32_rgb16' and info['color_converted']
    assert info['decoded_bits']==16 and info['source_bits']==16
    assert min(info['levels_per_channel'])>256


@pytest.mark.parametrize("decode_ms", [-1, float("nan"), float("inf")])
def test_edited_rgb16_invalid_timing_rejected_before_output(tmp_path, decode_ms):
    from types import SimpleNamespace
    path = tmp_path / "must-not-exist.tif"
    decoded = SimpleNamespace(rgb=gradient(8,8), raw={})
    with pytest.raises(ex.ExportError, match="decode_ms"):
        ex.export_edited_16bit(decoded, ex.ExportSpec(strength=0), str(path), decode_ms=decode_ms)
    assert not path.exists()


def test_rgb16_raw_report_does_not_invent_sensor_bit_depth(tmp_path):
    pytest.importorskip('torch')
    from lumaretouch_engine.ops import libraw as lr
    from lumaretouch_engine.decode import load_full
    if not lr.available(): pytest.skip('LibRaw unavailable')
    decoded=load_full(lr.PROBE_DNG,want_bits=16,device='cpu')
    info=ex.export_edited_16bit(decoded,ex.ExportSpec(strength=0,exposure=(.23,0,0,0,0,0,0)),str(tmp_path/'raw.tif'),device='cpu')
    assert info['decoded_bits']==16
    assert info['source_bits'] is None  # Sensor file precision was not extracted.
    assert info['readback_max_diff']==0
