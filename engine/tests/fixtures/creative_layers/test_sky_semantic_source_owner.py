"""AUTHORED / UNRUN: canonical source packet cache and exact native admission."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_sky as C
from lumaretouch_engine import creative_derived_source as D
from lumaretouch_engine import creative_document_base as B
from lumaretouch_engine import creative_document_host as H
from lumaretouch_engine import creative_sky_host as G
from lumaretouch_engine.sky_semantic import immutable_input as I


SOURCE={'sha256':'1'*64,'width':8,'height':6}


def owner(monkeypatch):
    record={'id':'sha256:'+'1'*64,'width':8,'height':6}
    engine=SimpleNamespace()
    monkeypatch.setattr(D,'record',lambda e:record)
    monkeypatch.setattr(D,'binding',lambda e:deepcopy(SOURCE))
    monkeypatch.setattr(D,'verify',lambda source,e:source)
    monkeypatch.setattr(H,'memory_budget',lambda:512_000_000)
    return engine,record


def test_packet_uses_full_canonical_pixels_not_display_analysis(monkeypatch):
    engine,record=owner(monkeypatch)
    pixels=np.linspace(0,1,6*8*3,dtype=np.float32).reshape(6,8,3)
    calls=[]
    def export(actual,**kwargs):
        assert actual is record
        calls.append(actual['id'])
        return pixels
    monkeypatch.setattr(B,'export_source',export)
    monkeypatch.setattr(D,'analysis_rgb',lambda e:pytest.fail('Display analysis is not model input'))
    packet=C.semantic_input(engine)
    assert packet==I.from_pixels(pixels,SOURCE)
    assert C.semantic_input(engine)==packet and len(calls)==1
    packet['source']['sha256']='2'*64
    assert C.semantic_input(engine)['source']==SOURCE


def test_canonical_alpha_hdr_refusal_is_not_replaced_by_proxy(monkeypatch):
    engine,_=owner(monkeypatch)
    def refused(*args,**kwargs):raise ValueError('alpha/HDR source cannot enter portrait RGB')
    monkeypatch.setattr(B,'export_source',refused)
    with pytest.raises(ValueError,match='alpha/HDR'):C.semantic_input(engine)
    assert not hasattr(engine,'_creative_sky_semantic_input')


def test_cached_canonical_metadata_cannot_be_relabelled(monkeypatch):
    engine,_=owner(monkeypatch)
    monkeypatch.setattr(B,'export_source',lambda *a,**k:np.full((6,8,3),.4,np.float32))
    C.semantic_input(engine)
    engine._creative_sky_semantic_input[1]['canonical_sha256']='e'*64
    with pytest.raises(ValueError,match='cache changed'):C.semantic_input(engine)


def test_source_budget_refuses_before_conversion(monkeypatch):
    engine,_=owner(monkeypatch)
    monkeypatch.setattr(H,'memory_budget',lambda:1)
    monkeypatch.setattr(B,'export_source',lambda *a,**k:pytest.fail('Budget must precede conversion'))
    with pytest.raises(ValueError,match='bounded memory'):C.semantic_input(engine)


def request(action='start'):
    value={'cmd':'sky_semantic','action':action,'request_id':'a'*32,
        'run_id':'a'*32,'session_id':'b'*32,'document_id':'doc'}
    if action=='start':value['device']='cpu'
    return value


def test_exact_cancel_can_release_stale_source_without_capture(monkeypatch):
    monkeypatch.setattr(C,'preview',lambda *a:pytest.fail('Stale cancel must not acquire source'))
    G.require_command(SimpleNamespace(),'sky_semantic',request('cancel'))


def test_start_requires_presented_locator_and_canonical_capture(monkeypatch):
    engine,_=owner(monkeypatch);calls=[]
    monkeypatch.setattr(C,'preview',lambda *a:None)
    monkeypatch.setattr(C,'semantic_input',lambda e:calls.append('canonical'))
    engine._sky_replacement_preview_owner=SimpleNamespace(matching=lambda p:{'shown':False})
    with pytest.raises(ValueError,match='Present'):G.require_command(engine,'sky_semantic',request())
    assert not calls
    engine._sky_replacement_preview_owner.matching=lambda p:{'shown':True}
    G.require_command(engine,'sky_semantic',request())
    assert calls==['canonical']


@pytest.mark.parametrize('change',[{'device':'auto'},{'run_id':'c'*32},{'path':'original.jpg'},{'action':'apply'}])
def test_semantic_admission_rejects_fallback_or_edit_envelopes(monkeypatch,change):
    engine,_=owner(monkeypatch)
    monkeypatch.setattr(C,'preview',lambda *a:None)
    engine._sky_replacement_preview_owner=SimpleNamespace(matching=lambda p:{'shown':True})
    with pytest.raises(ValueError):G.require_command(engine,'sky_semantic',{**request(),**change})
