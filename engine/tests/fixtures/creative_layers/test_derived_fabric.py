"""AUTHORED / UNRUN: source ownership fixtures, not fabric visual acceptance."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_fabric as F,creative_derived_source as D
from lumaretouch_engine import creative_derived_masks as M,fabric_export as E


def context():
    mask=np.ones((4,5),np.float32)
    vectors=np.array([[.1,.2]],np.float64)
    source={'sha256':'1'*64,'width':10,'height':8}
    return {'version':1,'source':source,'original_sha256':'2'*64,
        'analysis':{**source,'proxy_width':5,'proxy_height':4,'proxy_sha256':'3'*64},
        'semantic_owner':{'backend':'mediapipe','contract':'mediapipe-selfie-multiclass-six-classes-v1:'+'4'*64},
        'mask':mask,'mask_sha256':F._hash(mask),'scale_vectors':vectors,'scale_sha256':F._hash(vectors)}


def test_context_rejects_foreign_mask_and_scale():
    value=context();assert F.verify_context(value,value['source']) is value
    for key in ('mask','scale_vectors'):
        changed=deepcopy(value);changed[key][0,0]+=.01
        with pytest.raises(ValueError):F.verify_context(changed,value['source'])
    with pytest.raises(ValueError):F.verify_context(value,{**value['source'],'sha256':'5'*64})
    bad=deepcopy(value);bad['analysis']['sha256']='5'*64
    with pytest.raises(ValueError):F.verify_context(bad,value['source'])


def test_scale_retains_existing_normalized_measurement():
    value=context()
    assert F.face_scale(value,80,100)==pytest.approx(np.linalg.norm([10,16]))
    value['scale_vectors']=np.empty((0,2),np.float64)
    assert F.face_scale(value,80,100) is None


def test_full_export_needs_canonical_pixels_and_owned_repair(monkeypatch):
    value=context();source=np.full((8,10,3),.4,np.float32)
    spec=SimpleNamespace(creative_base=object(),creative_fabric_context=value,repair=[])
    monkeypatch.setattr(D,'binding',lambda state:value['source'])
    with pytest.raises(ValueError):F.export_pixels(spec,source,None,1.)
    F.stamp_pixels(spec,source)
    assert F.export_pixels(spec,source,None,1.) is source
    with pytest.raises(ValueError):F.export_pixels(spec,source,None,255.)
    bad=source.copy();bad[0,0,0]+=.01
    with pytest.raises(ValueError):F.export_pixels(spec,bad,None,1.)
    with pytest.raises(ValueError):F.export_pixels(spec,source,source.copy(),1.)
    spec.repair=[object()]
    with pytest.raises(ValueError):F.export_pixels(spec,source,None,1.)


def test_export_uses_full_float_without_integer_roundtrip(monkeypatch):
    value=context();source=np.full((8,10,3),.400001,np.float32)
    spec=SimpleNamespace(creative_base=object(),creative_fabric_context=value,repair=[],
        fabric_amount=.5,fabric_mask=np.ones((8,10),np.float32),fabric_face_px=2.)
    monkeypatch.setattr(D,'binding',lambda state:value['source'])
    F.stamp_pixels(spec,source)
    spec._creative_fabric_resampled=(F._hash(spec.fabric_mask),2.)
    seen=[]
    monkeypatch.setattr(E,'measure_field',lambda rgb,mask,scale:seen.append(rgb) or mask)
    E.prepare_export(spec,source,None,1.)
    assert seen[0] is source
    spec.fabric_mask[0,0]=0
    with pytest.raises(ValueError):E.prepare_export(spec,source,None,1.)


def test_exact_command_and_zero_clear_do_not_require_inference(monkeypatch):
    engine=SimpleNamespace(_load_id='doc')
    monkeypatch.setattr(F,'preview',lambda _:(_ for _ in ()).throw(ValueError('unanalysed')))
    F.require_command(engine,{'cmd':'fabric','action':'clear','document_id':'doc'})
    with pytest.raises(ValueError):F.require_command(engine,{'cmd':'fabric','amount':.3,'document_id':'doc'})
    with pytest.raises(ValueError):F.require_command(engine,{'cmd':'fabric','action':'clear','document_id':'other'})
    with pytest.raises(ValueError):F.require_command(engine,{'cmd':'fabric','action':'clear','document_id':'doc','mask':[]})
