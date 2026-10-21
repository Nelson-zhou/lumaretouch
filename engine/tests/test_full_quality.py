"""Full-source inspection core; does not pretend the UI 100% mode is wired."""
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import full_quality as F
from lumaretouch_engine.export import ExportSpec, ExportError, export_image, render_edited_rgb16
from lumaretouch_engine.ops.geometry import crop_rotate_np
from lumaretouch_engine.ops.curves import default_curves


def decoded(bits=8):
    dtype=np.uint16 if bits==16 else np.uint8
    rgb=np.random.default_rng(8).integers(0,65536 if bits==16 else 256,(64,96,3),dtype=dtype)
    return SimpleNamespace(rgb=rgb,src_w=96,src_h=64,src_bits=bits,draft_used=False,
                           raw=None,source_icc=None,fmt='TIFF' if bits==16 else 'PNG',notes=[])


def run(d,spec=None,roi=(2,3,12,9),**kw):
    return F.render_inspection_roi(d,spec or ExportSpec(strength=0),roi,
        max_source_pixels=6144,max_display_pixels=4096,device='cpu',tile=256,**kw)


def test_proxy_and_low_precision_inputs_are_not_labeled_full_quality():
    for field,value in [('src_w',192),('draft_used',True),('raw',{'source':'libraw_preview'}),('raw',{'source':'self_dng'}),('raw',{'source':'libraw'}),('src_bits',16)]:
        d=decoded();setattr(d,field,value)
        with pytest.raises(ExportError):run(d)


def test_half_size_raw_cannot_hide_behind_matching_decoded_dimensions():
    d=decoded(16);d.raw={'source':'libraw','half_size':True}
    with pytest.raises(ExportError):run(d)


def test_missing_layers_and_bad_roi_fail_before_render(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('renderer must not be called')
    monkeypatch.setattr(F,'export_image',forbidden)
    with pytest.raises(ExportError):run(decoded(),skipped_layers=['skin_mask'])
    for roi in [(0,0,0,1),(95,0,2,1),(0,0,1.2,1),(-1,0,1,1)]:
        with pytest.raises(ValueError):run(decoded(),roi=roi)
    with pytest.raises(ExportError):run(decoded(),spec=ExportSpec(strength=0,scale=2))
    with pytest.raises(F.RefinementCancelled):run(decoded(),cancelled=lambda:True)


@pytest.mark.parametrize('bits',[8,16])
@pytest.mark.parametrize('rotation',[0.,90.,17.])
def test_roi_equals_shared_export_pixels_after_geometry_and_curves(bits,rotation):
    pytest.importorskip('torch')
    d=decoded(bits);before=d.rgb.copy()
    curve=default_curves();curve['red']=[[0,.1],[1,.9]]
    spec=ExportSpec(strength=0,curves=curve)
    rect=(.1,.1,.9,.9)
    got=run(d,spec,rotation_degrees=rotation,crop_rect=rect)
    if bits==16:
        full,_,_=render_edited_rgb16(d,spec,device='cpu',tile=256,crop_rect=rect,rotation_degrees=rotation)
        expected=((full[3:12,2:14].astype(np.uint32)+128)//257).astype(np.uint8)
    else:
        full,_=export_image(d.rgb,spec,device='cpu',tile=256)
        full=crop_rotate_np(full,rect,rotation)
        expected=full[3:12,2:14]
    np.testing.assert_array_equal(got.rgba[...,:3],expected)
    np.testing.assert_array_equal(d.rgb,before)
    assert got.roi==(2,3,12,9) and got.decoded_bits==bits and np.all(got.rgba[...,3]==255)
    assert got.rgba.shape==(9,12,4)


def test_cancelled_render_is_never_returned(monkeypatch):
    d=decoded();calls=0
    def cancelled():return calls>0
    def render(*a,**kw):
        nonlocal calls
        calls+=1
        return d.rgb.copy(),{}
    monkeypatch.setattr(F,'export_image',render)
    with pytest.raises(F.RefinementCancelled):run(d,cancelled=cancelled)


def test_tiff_preserves_known_source_precision_metadata(monkeypatch):
    d=decoded(16);d.raw={'source':'tiff16'}
    monkeypatch.setattr(F,'render_edited_rgb16',lambda *a,**kw:(d.rgb.copy(),None,{}))
    got=run(d)
    assert got.decoded_bits==16 and got.source_bits==16
