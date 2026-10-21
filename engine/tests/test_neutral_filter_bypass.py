"""Neutral skin strength skips work, not other edits or parameter validation."""
import numpy as np
import pytest
pytest.importorskip('torch')
import torch
from lumaretouch_engine.vram import PreviewPipeline
from lumaretouch_engine.ops.curves import default_curves


def make(side=64):
    src=np.random.default_rng(7).integers(0,256,(side,side,3),dtype=np.uint8)
    pipe=PreviewPipeline('cpu',side,side);pipe.load_rgb_u8(src)
    return pipe,src


def test_small_neutral_image_never_builds_bands_or_filtered_result(monkeypatch):
    pipe,src=make(16)
    def forbidden(*a,**kw):raise AssertionError('neutral frame performed filtering')
    monkeypatch.setattr(pipe,'prepare',forbidden)
    monkeypatch.setattr(pipe,'lighten_result',forbidden)
    pipe.render(0.)
    np.testing.assert_array_equal(pipe.read_back()[...,:3],src)
    assert pipe.bands is None and pipe.retouched is None
    assert pipe.filter_resident_bytes()==0
    assert pipe.last_filter_ms==pipe.last_bands_ms==0


def test_zero_strength_keeps_existing_cache_identity_and_does_not_fake_new_key():
    pipe,_=make();pipe.render(.5,radius=6)
    cached=pipe.retouched;bands=pipe.bands;key=pipe.filter_key
    pipe.render(0.,radius=8)
    assert pipe.retouched is cached and pipe.bands is bands and pipe.filter_key==key
    pipe.render(.5,radius=6)
    assert pipe.retouched is cached and pipe.last_filter_ms==0
    pipe.render(.5,radius=8)
    assert pipe.retouched is not cached and pipe.filter_key!=key


def test_neutral_still_rejects_bad_parameters_and_unavailable_masks():
    pipe,_=make(16)
    for opts in ({'eps':0},{'radius':-1},{'detail_gain':float('nan')}):
        with pytest.raises(ValueError):pipe.render(0.,**opts)
    with pytest.raises(RuntimeError,match='没有可用掩膜'):pipe.render(0.,channel='skin')
    pipe.masks_gpu=torch.ones((1,1,16,16));pipe.mask_names=['skin']
    with pytest.raises(KeyError):pipe.render(0.,channel='unknown')


def test_neutral_preserves_color_edits_without_mutating_source():
    pipe,src=make();source=pipe.src_f32.clone()
    spec=default_curves();spec['red']=[[0,.1],[1,1]]
    pipe.set_curves(spec);pipe.set_exposure(.25,0,0)
    pipe.render(0.);first=pipe.read_back().copy()
    assert np.any(first[...,:3]!=src)
    torch.testing.assert_close(pipe.src_f32,source,rtol=0,atol=0)
    pipe.render(0.);np.testing.assert_array_equal(pipe.read_back(),first)
    torch.testing.assert_close(pipe.src_f32,source,rtol=0,atol=0)


def test_neutral_preserves_repair_and_light_source_and_their_buffers(monkeypatch):
    pipe,_=make();pipe.repair_base=pipe.src_f32*.8
    repair=pipe.repair_base.clone();lit=pipe.repair_base*.9;before=lit.clone()
    monkeypatch.setattr(pipe,'lighten_source',lambda:lit)
    result=pipe.retouch(0.)
    torch.testing.assert_close(result,lit,rtol=0,atol=0)
    torch.testing.assert_close(pipe.repair_base,repair,rtol=0,atol=0)
    torch.testing.assert_close(lit,before,rtol=0,atol=0)
