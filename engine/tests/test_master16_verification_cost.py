from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import export as ex
from lumaretouch_engine import decode


def test_master_total_time_includes_verification_statistics(monkeypatch,tmp_path):
    a=np.arange(24*32*3,dtype=np.uint16).reshape(24,32,3)
    d=SimpleNamespace(rgb=a,raw={'source':'test_uint16'},source_icc=None,src_w=32,src_h=24,fmt='TIFF',notes=[])
    monkeypatch.setattr(decode,'load_full',lambda *a,**k:d)
    clock=SimpleNamespace(value=0.0)
    monkeypatch.setattr(ex,'time',SimpleNamespace(perf_counter=lambda:clock.value))
    original=np.count_nonzero
    def measured(*args,**kwargs):
        clock.value+=.1
        return original(*args,**kwargs)
    monkeypatch.setattr(np,'count_nonzero',measured)
    got=ex.export_master_16bit('input',str(tmp_path/'out.tif'),output_profile='none')
    assert clock.value>0
    assert got['total_ms'] == pytest.approx(clock.value*1000)
    assert got['readback_max_diff']==0


def test_verification_is_chunk_bounded_and_matches_full_reference(monkeypatch):
    rng=np.random.default_rng(2106)
    a=rng.integers(0,65536,size=(41,73,3),dtype=np.uint16)
    b=a.copy();b[12,30,1]=0
    want_diff=int(np.max(np.abs(a.astype(np.int32)-b.astype(np.int32))))
    want_levels=[np.unique(b[...,c]).size for c in range(3)]
    want_low=int(np.count_nonzero(b & 255))
    original=np.bincount;seen=[]
    def counted(values,*args,**kwargs):
        seen.append(values.size)
        assert values.size<=31
        return original(values,*args,**kwargs)
    monkeypatch.setattr(np,'bincount',counted)
    facts=ex._rgb16_readback_facts(a[:,::-1],b[:,::-1],chunk_pixels=31)
    assert facts['readback_max_diff']==want_diff
    assert facts['levels_per_channel']==want_levels
    assert facts['low8_nonzero_px']==want_low
    assert seen and max(seen)<=31


def test_verification_does_not_wrap_uint16_difference():
    a=np.zeros((2,3,3),np.uint16);b=a.copy();b[1,2,0]=65535
    assert ex._rgb16_readback_facts(a,b)['readback_max_diff']==65535


def test_shape_mismatch_is_reported_not_hidden():
    a=np.zeros((2,3,3),np.uint16);b=np.full((3,2,3),257,np.uint16)
    facts=ex._rgb16_readback_facts(a,b,chunk_pixels=2)
    assert facts=={'readback_max_diff':-1,'levels_per_channel':[1,1,1],'low8_nonzero_px':18}


@pytest.mark.parametrize('budget',[0,-1])
def test_nonpositive_chunk_budget_is_rejected(budget):
    a=np.zeros((2,3,3),np.uint16)
    with pytest.raises(ValueError,match='positive'):
        ex._rgb16_readback_facts(a,a,chunk_pixels=budget)


def test_skipped_export_time_includes_preflight(monkeypatch,tmp_path):
    a=np.arange(24*32*3,dtype=np.uint16).reshape(24,32,3)
    d=SimpleNamespace(rgb=a,raw={'source':'test_uint16'},source_icc=None,src_w=32,src_h=24,fmt='TIFF',notes=[])
    monkeypatch.setattr(decode,'load_full',lambda *a,**k:d)
    clock=SimpleNamespace(value=0.0)
    monkeypatch.setattr(ex,'time',SimpleNamespace(perf_counter=lambda:clock.value))
    path=str(tmp_path/'out.tif')
    ex.export_master_16bit('input',path,output_profile='none')
    original=ex.write_tiff16
    def measured(*args,**kwargs):
        result=original(*args,**kwargs);clock.value+=.2;return result
    monkeypatch.setattr(ex,'write_tiff16',measured)
    got=ex.export_master_16bit('input',path,output_profile='none')
    assert got['skipped'] is True
    assert got['total_ms']==pytest.approx(200)


@pytest.mark.parametrize('corrupt',['pixels','icc'])
def test_failed_readback_cannot_be_reported_as_success(monkeypatch,tmp_path,corrupt):
    a=np.arange(24*32*3,dtype=np.uint16).reshape(24,32,3)
    d=SimpleNamespace(rgb=a,raw={'source':'test_uint16'},source_icc=None,src_w=32,src_h=24,fmt='TIFF',notes=[])
    monkeypatch.setattr(decode,'load_full',lambda *a,**k:d)
    if corrupt=='pixels':
        original=ex.read_tiff16
        def changed(*args,**kwargs):
            b=original(*args,**kwargs).copy();b[0,0,0]^=1;return b
        monkeypatch.setattr(ex,'read_tiff16',changed)
    else:
        monkeypatch.setattr(ex,'read_tiff16_icc',lambda *a,**k:b'not the written profile')
    path=tmp_path/'out.tif'
    with pytest.raises(ex.ExportError,match='验证失败'):
        ex.export_master_16bit('input',str(path),output_profile='srgb')
    assert path.exists(), 'failed file stays available for inspection, never silently deleted'
