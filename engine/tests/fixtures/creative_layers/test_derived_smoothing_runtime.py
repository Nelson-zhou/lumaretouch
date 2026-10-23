"""AUTHORED / UNRUN: smoothing consumer fences, not visual/runtime acceptance."""
from types import SimpleNamespace
import numpy as np
import pytest
import torch
from lumaretouch_engine import creative_derived_smoothing_runtime as R
from lumaretouch_engine import vram as V


def fixture():
    source={'sha256':'a'*64,'width':8,'height':8}
    pixels=np.full((8,8,3),.4,np.float32)
    pipe=SimpleNamespace(h=8,w=8,src_f32=torch.from_numpy(pixels.transpose(2,0,1).copy())[None],
        repair_base=None,_creative_repair_source=source,repair_version=1,
        masks_gpu=torch.ones((1,1,8,8)),mask_names=['skin'],retouched=None,filter_key=None,
        bands=None,bands_key=None,device=torch.device('cpu'))
    pipe.base=lambda:pipe.src_f32 if pipe.repair_base is None else pipe.repair_base
    pipe.mask=lambda channel:pipe.masks_gpu[pipe.mask_names.index(channel):pipe.mask_names.index(channel)+1]
    return pipe,source,pixels


def test_actual_base_and_mask_are_required_before_binding():
    pipe,source,pixels=fixture()
    with pytest.raises(ValueError):R.check(pipe,'skin',require=True)
    with pytest.raises(ValueError):R.bind(pipe,source,pixels+.01)
    with pytest.raises(ValueError):R.bind(pipe,source,pixels,mask_channel='skin',mask_pixels=np.zeros((8,8),np.float32))
    R.bind(pipe,source,pixels,mask_channel='skin',mask_pixels=np.ones((8,8),np.float32))
    assert R.check(pipe,'skin',require=True)[0]==source['sha256']
    with pytest.raises(ValueError):R.check(pipe,None,require=True)
    pipe.masks_gpu[0,0,0,0]=0
    with pytest.raises(ValueError):R.check(pipe,'skin',require=True)


def test_source_repair_and_identity_changes_invalidate_owned_binding():
    pipe,source,pixels=fixture();R.bind(pipe,source,pixels)
    pipe.src_f32[0,0,0,0]+=.01
    with pytest.raises(ValueError):R.check(pipe,require=True)
    pipe,source,pixels=fixture();R.bind(pipe,source,pixels)
    pipe.repair_base=pipe.src_f32.clone()
    with pytest.raises(ValueError):R.check(pipe,require=True)
    pipe,source,pixels=fixture();R.bind(pipe,source,pixels)
    pipe._creative_repair_source={**source,'sha256':'b'*64}
    with pytest.raises(ValueError):R.check(pipe,require=True)


def test_filter_hotpath_reuses_bands_and_rejects_mutated_result(monkeypatch):
    pipe,source,pixels=fixture();R.bind(pipe,source,pixels)
    pipe._filter_parameters=V.PreviewPipeline._filter_parameters
    calls=[]
    monkeypatch.setattr(V,'bands_t',lambda value,**kw:calls.append('bands') or (value.clone(),)*4)
    monkeypatch.setattr(V,'combine_t',lambda *args,**kw:calls.append('combine') or args[0].clone())
    V.PreviewPipeline.prepare(pipe,radius=2,texture_radius=1)
    V.PreviewPipeline.prepare(pipe,radius=2,texture_radius=1)
    assert calls==['bands','combine'] and pipe.last_filter_ms==0 and pipe.last_bands_ms==0
    V.PreviewPipeline.prepare(pipe,radius=2,texture_radius=1,detail_gain=1.1)
    assert calls==['bands','combine','combine']
    pipe.retouched[0,0,0,0]+=.01
    with pytest.raises(ValueError):V.PreviewPipeline.prepare(pipe,radius=2,texture_radius=1,detail_gain=1.1)


def test_export_tile_has_explicit_verified_float_domain_and_reset():
    pipe,source,pixels=fixture();pipe._creative_repair_source=None
    R.bind(pipe,source,pixels,domain='export-tile')
    assert R.check(pipe,require=True)[3]=='export-tile'
    R.reset(pipe)
    assert R.check(pipe,require=False) is None
    assert getattr(pipe,'_creative_smoothing_cache',None) is None


def test_rebinding_coverage_keeps_source_only_filter_cache():
    pipe,source,pixels=fixture();R.bind(pipe,source,pixels)
    result=pipe.retouched=pipe.src_f32.clone();pipe.filter_key=('existing',)
    pipe.bands=(pipe.src_f32.clone(),)*4;pipe.bands_key=('bands',)
    R.cache_record(pipe)
    R.bind(pipe,source,pixels,mask_channel='skin',mask_pixels=np.ones((8,8),np.float32),evidence_key='new-coverage')
    assert pipe.retouched is result and pipe.filter_key==('existing',)
    R.cache_check(pipe)
