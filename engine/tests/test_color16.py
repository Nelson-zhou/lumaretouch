"""ICC conversion must preserve precision and never relabel unconverted RGB16."""
import io
from pathlib import Path
import numpy as np
import pytest
from PIL import Image, ImageCms
from lumaretouch_engine.color16 import convert_rgb16
from lumaretouch_engine.export import _srgb_bytes, export_master_16bit, read_tiff16, read_tiff16_icc
import tifffile

PROFILE=Path(__file__).resolve().parent/'fixtures'/'icc'/'AdobeCompat-v2.icc'


def test_reference_profile_is_bundled_and_pinned():
    import hashlib
    data=PROFILE.read_bytes()  # Required fixture: absence fails, never silently skips.
    assert len(data)==374
    assert hashlib.sha256(data).hexdigest()=='60fb2adecacf82132db0b1c09b303316f3bbd9e2823e7ba096d01627d12d57c9'
    assert data[36:40]==b'acsp' and data[16:20]==b'RGB '


def ramp():
    x=np.arange(4096,dtype=np.uint16).reshape(64,64)
    return np.stack([x*13,x*7+2000,x*9+1000],axis=-1)


def test_same_profile_is_exact_uint16_identity():
    a=ramp();profile=_srgb_bytes()
    assert np.array_equal(a,convert_rgb16(a,profile,profile))


def test_rgb16_transform_agrees_with_independent_pillow8_reference_without_losing_levels():
    a=ramp();source=PROFILE.read_bytes();target=_srgb_bytes()
    out=convert_rgb16(a,source,target)
    reference=ImageCms.profileToProfile(Image.fromarray(np.rint(a/257).astype(np.uint8)),
        ImageCms.ImageCmsProfile(io.BytesIO(source)),ImageCms.ImageCmsProfile(io.BytesIO(target)),
        outputMode='RGB',renderingIntent=1,flags=8192)
    assert np.max(np.abs(np.rint(out/257).astype(int)-np.asarray(reference).astype(int))) <= 2
    assert out.dtype == np.uint16 and all(len(np.unique(out[...,c]))>256 for c in range(3))
    assert np.any(out != a) and np.any(out & 255)


@pytest.mark.parametrize('bad',[b'',b'broken ICC'])
def test_invalid_profile_rejected_even_if_identical(bad):
    with pytest.raises(ValueError,match='ICC'):convert_rgb16(ramp(),bad,bad)


def test_wrong_colorspace_rejected():
    lab=ImageCms.ImageCmsProfile(ImageCms.createProfile('LAB')).tobytes()
    with pytest.raises(ValueError,match='RGB'):convert_rgb16(ramp(),lab,_srgb_bytes())


@pytest.mark.parametrize('target',['source','srgb'])
def test_master16_uses_source_profile_instead_of_retagging(tmp_path,target):
    a=ramp();profile=PROFILE.read_bytes();src=tmp_path/'source.tif';dst=tmp_path/'out.tif'
    tifffile.imwrite(src,a,photometric='rgb',iccprofile=profile)
    info=export_master_16bit(str(src),str(dst),output_profile=target)
    expected=a if target=='source' else convert_rgb16(a,profile,read_tiff16_icc(str(dst)))
    assert np.array_equal(read_tiff16(str(dst)),expected)
    assert info['readback_max_diff']==0
    assert info['color_converted'] == (target=='srgb')
    if target=='source':assert read_tiff16_icc(str(dst))==profile


def linear_srgb_profile():
    """Create a synthetic, redistributable calibration profile using public lcms API."""
    import ctypes as C
    from lumaretouch_engine.color16 import _library
    class xyY(C.Structure):
        _fields_=[('x',C.c_double),('y',C.c_double),('Y',C.c_double)]
    class Triple(C.Structure):
        _fields_=[('Red',xyY),('Green',xyY),('Blue',xyY)]
    lib=_library()
    lib.cmsBuildGamma.argtypes=[C.c_void_p,C.c_double];lib.cmsBuildGamma.restype=C.c_void_p
    lib.cmsFreeToneCurve.argtypes=[C.c_void_p];lib.cmsFreeToneCurve.restype=None
    lib.cmsCreateRGBProfile.argtypes=[C.POINTER(xyY),C.POINTER(Triple),C.POINTER(C.c_void_p)]
    lib.cmsCreateRGBProfile.restype=C.c_void_p
    lib.cmsSaveProfileToMem.argtypes=[C.c_void_p,C.c_void_p,C.POINTER(C.c_uint32)]
    lib.cmsSaveProfileToMem.restype=C.c_int
    white=xyY(.3127,.3290,1);prim=Triple(xyY(.64,.33,1),xyY(.30,.60,1),xyY(.15,.06,1))
    curve=lib.cmsBuildGamma(None,1.0);profile=None
    try:
        profile=lib.cmsCreateRGBProfile(C.byref(white),C.byref(prim),(C.c_void_p*3)(curve,curve,curve))
        assert profile
        size=C.c_uint32()
        assert lib.cmsSaveProfileToMem(profile,None,C.byref(size))
        data=C.create_string_buffer(size.value)
        assert lib.cmsSaveProfileToMem(profile,data,C.byref(size))
        return data.raw[:size.value]
    finally:
        if profile:lib.cmsCloseProfile(profile)
        if curve:lib.cmsFreeToneCurve(curve)


def test_synthetic_linear_profile_follows_srgb_transfer_at_16bit_precision():
    x=np.arange(65536,dtype=np.uint16).reshape(256,256)
    a=np.repeat(x[...,None],3,axis=-1)
    out=convert_rgb16(a,linear_srgb_profile(),_srgb_bytes())
    lin=x.astype(np.float64)/65535
    expected=np.rint(np.where(lin<=.0031308,12.92*lin,1.055*lin**(1/2.4)-.055)*65535)
    error=np.abs(out.astype(np.float64)-expected[...,None])
    assert error.max() <= 16, error.max()
    assert all(len(np.unique(out[...,c])) > 30000 for c in range(3))


def test_master_color_conversion_with_generated_profile_has_no_optional_asset(tmp_path):
    a=ramp();profile=linear_srgb_profile();src=tmp_path/'input.tif'
    tifffile.imwrite(src,a,photometric='rgb',iccprofile=profile)
    dest=tmp_path/'out.tif'
    info=export_master_16bit(str(src),str(dest),output_profile='srgb')
    assert info['color_converted'] and info['icc_readback_matches']
    assert np.array_equal(read_tiff16(str(dest)),convert_rgb16(a,profile,read_tiff16_icc(str(dest))))
