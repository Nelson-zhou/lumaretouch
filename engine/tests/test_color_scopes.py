"""Independent bounded Rust colour analysis and stage-sampling contracts."""
from pathlib import Path
import subprocess
import numpy as np
import pytest
from lumaretouch_engine.color_scopes_sampling import Sample,grid_shape,gather,sample_stage,MAX_SAMPLES
from lumaretouch_engine.color_scopes_bridge import analyze


def sample(pixels):
    data=np.asarray(pixels,np.float32).reshape(1,-1,3)
    return Sample(data,data.shape[1],1,data.shape[1],1)


def test_rust_bins_count_out_of_range_and_nonfinite_separately():
    result=analyze(sample([[0,0,0],[1,1,1],[.5,.5,.5],[-.1,1.1,0],[float('nan'),0,0]]))
    assert result['samples']==5 and result['finite_samples']==4 and result['nonfinite_samples']==1
    assert result['rgb'][0]['underflow']==1 and result['rgb'][1]['overflow']==1
    assert result['rgb'][0]['bins'][255]==1
    assert result['linear_y']['bins'][255]==1  # white is not a numerical overflow
    for channel in result['rgb']:
        assert sum(channel['bins'])+channel['underflow']+channel['overflow']==4


def test_rust_lab_d65_matches_existing_in_gamut_quality_reference():
    from lumaretouch_engine.color_metric import srgb_to_lab
    for rgb in [[0,0,0],[1,1,1],[1,0,0],[.2,.4,.7],[.9,.1,.3]]:
        result=analyze(sample([rgb]))
        expected=srgb_to_lab(np.asarray(rgb)*255)
        np.testing.assert_allclose(result['mean_lab_d65'],expected,rtol=0,atol=2e-5)
    result=analyze(sample([[0,0,0],[1,1,1]]))
    np.testing.assert_allclose(result['mean_srgb'],[.5,.5,.5],atol=0)
    np.testing.assert_allclose(result['mean_lab_d65'],srgb_to_lab(np.array([127.5]*3)),atol=1e-6)


def test_binary_worker_rejects_truncation_trailing_and_oversized_input():
    from lumaretouch_engine import color_scopes_bridge as bridge
    worker=Path(bridge.__file__).parent/'bin/color-scopes'
    for data in [b'',b'LCS1',b'LCS1'+(1).to_bytes(4,'little')+bytes(13),bytes(8+MAX_SAMPLES*12+1)]:
        result=subprocess.run([str(worker)],input=data,capture_output=True,timeout=5)
        assert result.returncode==2 and not result.stdout


def test_grid_covers_extreme_aspect_ratios_with_bounded_size():
    for width,height in [(1,10000000),(10000000,1),(10000,10000),(13,17),(1,1)]:
        gw,gh=grid_shape(width,height)
        assert 1<=gw<=width and 1<=gh<=height and gw*gh<=MAX_SAMPLES
        if width*height<=MAX_SAMPLES:assert (gw,gh)==(width,height)
    for size in [(0,1),(1,0),(-1,1)]:
        with pytest.raises(ValueError):grid_shape(*size)


def test_gather_is_owned_bounded_and_spans_both_edges():
    torch=pytest.importorskip('torch')
    source=torch.arange(3*10000,dtype=torch.float32).reshape(1,3,1,10000)
    result=gather(source,budget=100)
    assert result.pixels.size<=300 and result.grid_width*result.grid_height<=100
    assert result.pixels[0,0,0]<100 and result.pixels[-1,-1,0]>9000
    before=result.pixels.copy();source.zero_();np.testing.assert_array_equal(result.pixels,before)


def test_pipeline_taps_do_not_change_pixels_or_packed_buffer():
    pytest.importorskip('torch')
    from lumaretouch_engine.vram import PreviewPipeline
    from lumaretouch_engine.ops.levels import default_levels
    src=np.full((64,80,3),100,np.uint8);pipe=PreviewPipeline(device='cpu',w=80,h=64);pipe.load_rgb_u8(src)
    levels=default_levels();levels['master']['gamma']=2;pipe.set_levels(levels)
    pipe.render(0);packed=pipe.read_back().copy()
    before=pipe.retouch(0).clone()
    inputs=sample_stage(pipe,'levels-input',0,None,{})
    curves=sample_stage(pipe,'curves-input',0,None,{})
    output=sample_stage(pipe,'output',0,None,{})
    original=sample_stage(pipe,'original',0,None,{})
    np.testing.assert_allclose(inputs.pixels,100/255,atol=1e-6)
    np.testing.assert_allclose(original.pixels,inputs.pixels,atol=0)
    np.testing.assert_allclose(curves.pixels,np.sqrt(100/255),atol=1e-6)
    np.testing.assert_allclose(output.pixels,curves.pixels,atol=0)
    np.testing.assert_array_equal(pipe.read_back(),packed)
    assert pipe.retouch(0).equal(before)
