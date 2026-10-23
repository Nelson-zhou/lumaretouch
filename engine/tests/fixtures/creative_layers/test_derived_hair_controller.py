"""AUTHORED / UNRUN: derived hair evidence and review ownership contracts.

Synthetic model identities/pixels are fixtures, not inference or visual proof.
No product imports, tests or native rendering were run while authoring.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from test_derived_effects_contract import fixture
from lumaretouch_engine import hair_colour_controller as C, hair_colour_evidence as E
from lumaretouch_engine import hair_colour_assets as A, creative_derived_source as D


def setup(monkeypatch):
    import torch
    from lumaretouch_engine import people_host_commands as H
    engine,state,context,owned,rgb=fixture(monkeypatch)
    key=context['target']['target_id']
    state['faces'][key]['evidence']['semantic_model_sha256']=A.MODEL_SHA256
    engine._precompute.semantic_model_sha256=A.MODEL_SHA256
    engine._precompute.masks['hair']=np.ones((4,4),np.float32)
    engine._people_cursors={owned['sha256']:key}
    engine._people_owner=lambda:SimpleNamespace(snapshot=lambda:deepcopy(state),fence=0)
    engine._doc_path='/original/provenance-only.png'
    engine._vram=SimpleNamespace(src_f32=torch.from_numpy(rgb.copy()).permute(2,0,1)[None].float()/255.,repair_base=None)
    monkeypatch.setattr(H,'checked',lambda *a:(deepcopy(state),{},context['target']))
    return engine,state,context,owned,rgb


def stroke():
    return {'version':1,'domain':'source-normalized','objects':[
        {'id':'stroke','name':'fixture','enabled':True,'operation':'add','kind':'brush',
         'opacity':1.,'feather':1.,'points':[[.2,.2],[.3,.4]],'axes':[[.03,0],[0,.03]]}]}


def prompted(enabled):
    value=stroke();value['objects'].append({
        'id':'prompt','name':'fixture','enabled':enabled,'operation':'add','kind':'prompted',
        'opacity':1.,'feather':1.,'selection':{'prompts':{'points':[{'x':.3,'y':.3,'label':1}],'box':None},
            'candidate':0,'device':'cpu','input_sha256':'4'*64,
            'model':{'id':'synthetic-fixture','checkpoint_sha256':'5'*64,'config_sha256':'6'*64,
                     'code_revision':'7'*40,'contract':'fixture-not-inference'}}})
    return value


def test_new_evidence_uses_verified_actual_composite_analysis(monkeypatch):
    engine,_,_,owned,_=setup(monkeypatch)
    value=E.current(engine,owned)
    assert value['source']==owned and value['model_sha256']==A.MODEL_SHA256
    np.testing.assert_array_equal(value['weight'],engine._precompute.masks['hair'])
    assert E.for_source(engine._hair_colour_evidence,owned)['weight_sha256']==value['weight_sha256']


@pytest.mark.parametrize('change',[
    lambda e:setattr(e,'_precompute',None),
    lambda e:e._precompute.input_source_binding.update(sha256='f'*64),
    lambda e:setattr(e._precompute,'input_source_binding',None),
    lambda e:e._precompute.masks.update(hair=np.ones((2,2),np.float32)),
])
def test_new_evidence_refuses_missing_or_relabelled_analysis(monkeypatch,change):
    engine,_,_,owned,_=setup(monkeypatch);change(engine)
    with pytest.raises(ValueError):E.current(engine,owned)
    assert not engine.__dict__.get('_hair_colour_evidence')


def test_retained_exact_evidence_replays_without_model_but_not_foreign_binding(monkeypatch):
    engine,_,_,owned,_=setup(monkeypatch);saved=E.current(engine,owned)
    engine._precompute=None
    def forbidden(*a,**k):raise AssertionError('Inference evidence capture invoked on retained replay')
    monkeypatch.setattr(E.E,'capture',forbidden)
    assert E.current(engine,owned)['weight_sha256']==saved['weight_sha256']
    with pytest.raises(ValueError):E.current(engine,{**owned,'sha256':'f'*64})


def test_context_never_supplies_original_path_for_derived_review(monkeypatch):
    engine,_,context,owned,rgb=setup(monkeypatch)
    captured,_=C.context(engine,context)
    assert captured['source_path'] is None and captured['source']==owned
    np.testing.assert_allclose(C.rgb(engine),rgb.astype(np.float32)/255.,rtol=0,atol=np.finfo(np.float32).eps)
    assert engine._doc_path=='/original/provenance-only.png'


@pytest.mark.parametrize('change',[
    lambda e:setattr(e._vram,'src_f32',e._vram.src_f32*0),
    lambda e:setattr(e._vram,'repair_base',e._vram.src_f32),
    lambda e:e._precompute.input_source_binding.update(sha256='f'*64),
])
def test_context_refuses_original_pixels_repairs_or_stale_analysis(monkeypatch,change):
    engine,_,context,_,_=setup(monkeypatch);change(engine)
    with pytest.raises(ValueError):C.context(engine,context)


@pytest.mark.parametrize('enabled',[False,True])
def test_preview_rejects_even_disabled_prompted_support_before_evidence_capture(monkeypatch,enabled):
    engine,state,context,_,_=setup(monkeypatch);captured,_=C.context(engine,context)
    def forbidden(*a,**k):raise AssertionError('Evidence or inference reached for prompted support')
    monkeypatch.setattr(E,'current',forbidden)
    with pytest.raises(ValueError,match='prompted'):
        C.preview(engine,captured,state,'preview_support',{'mask':prompted(enabled)})


@pytest.mark.parametrize('enabled',[False,True])
def test_frozen_commit_cannot_bypass_prompted_support_refusal(monkeypatch,enabled):
    engine,state,context,owned,_=setup(monkeypatch);captured,_=C.context(engine,context)
    value=A.reviewed(context['target']['face_ref'],owned,prompted(enabled),A.MODEL_SHA256,
        evidence_sha='8'*64,confirmed=True)
    def forbidden(*a,**k):raise AssertionError('Graph or store publication began')
    monkeypatch.setattr(A,'retain',forbidden)
    with pytest.raises(ValueError,match='prompted'):C.publish(engine,captured,state,value)


def test_brush_and_radial_operator_recovery_preserve_exact_support(monkeypatch):
    engine,_,context,owned,_=setup(monkeypatch)
    support=stroke();recovery={'version':1,'domain':'source-normalized','objects':[
        {'id':'recover','name':'fixture','enabled':True,'operation':'add','kind':'radial',
         'opacity':.5,'feather':1.,'center':[.3,.3],'axes':[[.05,0],[0,.05]]}]}
    value=A.reviewed(context['target']['face_ref'],owned,support,A.MODEL_SHA256,
        evidence_sha='8'*64,confirmed=True,recovery=recovery)
    assert C.derived_record(engine,value)==value
    assert C.derived_record(engine,{**value,'recovery':A.empty_mask()})['support']==support
    assert C.derived_record(engine,None) is None


def test_review_context_change_refuses_before_commit(monkeypatch):
    engine,_,context,_,_=setup(monkeypatch);captured,_=C.context(engine,context)
    engine._people_owner=lambda:SimpleNamespace(fence=1)
    with pytest.raises(ValueError,match='改变'):C.assert_context(engine,captured)
