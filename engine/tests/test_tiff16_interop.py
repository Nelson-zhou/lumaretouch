"""External TIFF encodings preserve every bit, not only our own writer's layout."""
import numpy as np
import pytest
import tifffile
from lumaretouch_engine.decode import load_full


@pytest.mark.parametrize('compression',[None,'deflate','lzw'])
@pytest.mark.parametrize('byteorder',['<','>'])
@pytest.mark.parametrize('planar',['contig','separate'])
@pytest.mark.parametrize('bigtiff',[False,True])
def test_rgb16_external_encodings(tmp_path,compression,byteorder,planar,bigtiff):
    arr=((np.arange(19*23*3,dtype=np.uint32)*127+31)%65536).astype(np.uint16).reshape(19,23,3)
    src=arr if planar=='contig' else arr.transpose(2,0,1)
    path=tmp_path/'external.tif'
    tifffile.imwrite(path,src,photometric='rgb',planarconfig=planar,
                     compression=compression,byteorder=byteorder,bigtiff=bigtiff,rowsperstrip=4,
                     metadata=None)
    got=load_full(str(path),want_bits=16)
    assert got.rgb.dtype==np.uint16
    assert got.rgb.flags.c_contiguous
    assert np.array_equal(got.rgb,arr)


def test_pixel_limit_checked_before_decompression(tmp_path,monkeypatch):
    path=tmp_path/'limit.tif'
    tifffile.imwrite(path,np.zeros((20,30,3),np.uint16),photometric='rgb',compression='deflate')
    def forbidden(*a,**kw):
        raise AssertionError('decoded before resource limit check')
    monkeypatch.setattr(tifffile.TiffPage,'asarray',forbidden)
    with pytest.raises(ValueError,match='超过上限'):
        load_full(str(path),want_bits=16,max_px=100)


def test_float_tiff_not_silently_clipped_to_uint16(tmp_path):
    path=tmp_path/'float.tif'
    tifffile.imwrite(path,np.full((12,16,3),1.5,np.float32),photometric='rgb')
    with pytest.raises(ValueError,match='16-bit'):
        load_full(str(path),want_bits=16)


def test_tiled_rgb16(tmp_path):
    arr=np.arange(33*49*3,dtype=np.uint16).reshape(33,49,3)
    path=tmp_path/'tiles.tif'
    tifffile.imwrite(path,arr,photometric='rgb',tile=(16,16),compression='deflate')
    assert np.array_equal(load_full(str(path),want_bits=16).rgb,arr)


def test_multipage_requires_explicit_choice(tmp_path):
    path=tmp_path/'pages.tif'
    with tifffile.TiffWriter(path) as writer:
        for _ in range(2):
            writer.write(np.zeros((12,16,3),np.uint16),photometric='rgb')
    with pytest.raises(ValueError,match='多页'):
        load_full(str(path),want_bits=16)


def test_extra_alpha_is_not_silently_discarded(tmp_path):
    path=tmp_path/'rgba.tif'
    tifffile.imwrite(path,np.zeros((12,16,4),np.uint16),photometric='rgb')
    with pytest.raises(ValueError,match='三通道'):
        load_full(str(path),want_bits=16)


def test_bigtiff_rgb_is_not_misclassified_as_camera_raw(tmp_path):
    from lumaretouch_engine.decode import is_raw
    path=tmp_path/'rgb.tif'
    tifffile.imwrite(path,np.zeros((12,16,3),np.uint16),photometric='rgb',bigtiff=True)
    assert not is_raw(str(path))


def test_bigtiff_cfa_still_classified_as_camera_raw(tmp_path):
    from lumaretouch_engine.decode import is_raw
    path=tmp_path/'sensor.tif'
    tifffile.imwrite(path,np.zeros((12,16),np.uint16),photometric=32803,bigtiff=True)
    assert is_raw(str(path))
