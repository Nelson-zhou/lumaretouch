"""RGB16 lossless compression is encoding, not an image edit or precision loss."""
import numpy as np
import pytest
import tifffile
import imagecodecs
from lumaretouch_engine.export import write_tiff16, read_tiff16, read_tiff16_icc, _srgb_bytes


@pytest.mark.parametrize('compression,tag',[('none',1),('deflate',8),('lzw',5)])
def test_compressed16_roundtrips_through_independent_libtiff_decoder(tmp_path,compression,tag):
    a=np.random.default_rng(77).integers(0,65536,(47,71,3),dtype=np.uint16)
    path=tmp_path/f'{compression}.tif'
    result=write_tiff16(a,str(path),tiff_compression=compression)
    assert result['tiff_compression']==compression and result['tiff_compression_tag']==tag
    assert np.array_equal(read_tiff16(str(path)),a)
    assert np.array_equal(imagecodecs.tiff_decode(path.read_bytes()),a)
    assert read_tiff16_icc(str(path))==_srgb_bytes()
    with tifffile.TiffFile(path) as f:
        assert f.pages[0].compression==tag
        if compression!='none':assert f.pages[0].predictor==2


def test_predictor_compresses_smooth_gradient_without_changing_low_bits(tmp_path):
    x=np.arange(1024,dtype=np.uint16)[None,:,None]
    a=np.broadcast_to(x*61+3,(128,1024,3)).copy()
    raw=tmp_path/'raw.tif';small=tmp_path/'small.tif'
    write_tiff16(a,str(raw),tiff_compression='none')
    write_tiff16(a,str(small),tiff_compression='deflate')
    assert np.array_equal(imagecodecs.tiff_decode(small.read_bytes()),a)
    assert small.stat().st_size < raw.stat().st_size / 4

from test_protocol import engine, _collect_until


@pytest.mark.parametrize('compression',['deflate','lzw'])
def test_protocol_16bit_compression_reaches_real_file(engine,tmp_path,compression):
    pytest.importorskip('torch')
    a=np.random.default_rng(21).integers(0,65536,(64,80,3),dtype=np.uint16)
    src=tmp_path/'input.tif';tifffile.imwrite(src,a,photometric='rgb')
    engine.send(cmd='hello');engine.wait_for('ready')
    engine.send(cmd='set_device',device='cpu');engine.wait_for('device_set')
    engine.send(cmd='load_image',path=str(src),strength=0)
    engine.wait_for('image_ready',timeout=30)
    engine.send(cmd='export',format='tif',bit_depth=16,tiff_compression=compression,
                out_dir=str(tmp_path/'output'))
    done,_=_collect_until(engine,'export_done')
    assert done['failed']==0 and done['total']==1, done
    item=done['images'][0]
    assert item['tiff_compression']==compression
    assert item['verification_ms']>=0
    assert item['total_ms'] + .03 >= sum(item[k] for k in ('decode_ms','readback_ms','verification_ms'))
    assert np.array_equal(imagecodecs.tiff_decode(open(item['out'],'rb').read()),a)


def test_uncompressed_width_uses_32bit_tiff_dimension_tag(tmp_path):
    a=np.arange(65536*3,dtype=np.uint32).astype(np.uint16).reshape(1,65536,3)
    path=tmp_path/'wide.tif'
    write_tiff16(a,str(path),tiff_compression='none')
    assert np.array_equal(read_tiff16(str(path)),a)
    assert np.array_equal(imagecodecs.tiff_decode(path.read_bytes()),a)
