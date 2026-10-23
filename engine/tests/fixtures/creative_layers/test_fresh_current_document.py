"""AUTHORED / UNRUN: fresh-current capture and single history ownership."""
import struct
from copy import deepcopy
from types import SimpleNamespace
import pytest
from lumaretouch_engine.creative_document_assets import AssetStore, make_asset
from lumaretouch_engine import creative_document_state as S
from lumaretouch_engine import creative_document_host as H, creative_document_base as B
from lumaretouch_engine.creative_document_controller import CreativeController, CreativePorts
from lumaretouch_engine.creative_document_refresh import fresh_current


def fixture(monkeypatch):
    assets=AssetStore()
    old=make_asset('rgba',1,1,struct.pack('<ffff',.1,.2,.3,1.))
    new=make_asset('rgba',1,1,struct.pack('<ffff',.4,.2,.3,1.))
    assets.intern(old);assets.intern(new)
    document=S.create('photo-1',old['id'],assets)
    engine=SimpleNamespace(_creative_document=document,_doc_index=0,_docs=[{'document_id':'photo-1'}],
                           _capture_state=lambda:{'current_recipe':'owned'},owner='first')
    history=[];captures=[]
    def commit(after,before,label):
        history.append((deepcopy(before),label));engine._creative_document=after
    def capture(e,row,state,store,**kwargs):
        assert not kwargs['cancelled']()
        captures.append(deepcopy(state));return new
    monkeypatch.setattr(B,'capture_current_asset',capture)
    monkeypatch.setattr(H,'token',lambda e:e.owner)
    monkeypatch.setattr(H,'memory_budget',lambda:1024**2)
    monkeypatch.setattr(H,'rotate',lambda e:setattr(e,'owner','second'))
    ports=CreativePorts(lambda:engine._creative_document,lambda:engine.owner,lambda _:None,commit,lambda _:None,lambda:True)
    controller=CreativeController(ports,assets)
    host=SimpleNamespace(e=engine,assets=assets,controller=controller,commit_document=commit)
    envelope={'request_id':'fresh-1','document_id':document['document_id'],'source_uid':'photo-1',
              'expected_revision':0,'ownership_token':'first'}
    return host,envelope,history,captures,old,new


def test_fresh_current_captures_actual_recipe_and_retains_prior_document(monkeypatch):
    host,envelope,history,captures,old,new=fixture(monkeypatch)
    receipt=fresh_current(host,envelope)
    assert receipt['status']=='applied'
    assert captures==[{'current_recipe':'owned'}]
    assert host.e._creative_document['document_id']!=envelope['document_id']
    assert host.e._creative_document['source_asset']==new['id']
    assert len(history)==1 and history[0][0]['source_asset']==old['id']
    assert host.assets.get(old['id'])==old
    assert fresh_current(host,envelope)==receipt
    assert len(history)==len(captures)==1


def test_pending_return_and_stale_owner_refuse_before_capture(monkeypatch):
    host,envelope,history,captures,_,_=fixture(monkeypatch)
    host.controller.pending={'ticket_id':'pending'}
    with pytest.raises(ValueError):fresh_current(host,envelope)
    assert not captures and not history
    host.controller.pending=None;host.e.owner='changed'
    with pytest.raises(ValueError):fresh_current(host,envelope)
    assert not captures and not history


def test_failed_capture_leaves_document_and_history_unchanged(monkeypatch):
    host,envelope,history,captures,_,_=fixture(monkeypatch)
    before=deepcopy(host.e._creative_document)
    def fail(*args,**kwargs):raise ValueError('Unsupported current source recipe')
    monkeypatch.setattr(B,'capture_current_asset',fail)
    with pytest.raises(ValueError):fresh_current(host,envelope)
    assert host.e._creative_document==before and not history


def test_uncertain_commit_is_cached_and_never_repeated(monkeypatch):
    host,envelope,history,captures,_,_=fixture(monkeypatch)
    calls=[]
    def uncertain(after,before,label):
        calls.append(label)
        raise RuntimeError('Publication outcome unavailable')
    host.commit_document=uncertain
    with pytest.raises(RuntimeError,match='reconciliation'):fresh_current(host,envelope)
    result=fresh_current(host,envelope)
    assert result['status']=='unknown'
    assert len(calls)==len(captures)==1
