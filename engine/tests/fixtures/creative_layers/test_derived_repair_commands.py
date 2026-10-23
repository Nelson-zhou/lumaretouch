"""AUTHORED / UNRUN: derived reviewed repair proof, not runtime acceptance."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_repair_commands as C
from lumaretouch_engine import creative_derived_source as D
from lumaretouch_engine.source_patch_controller import SourcePatchController,SourcePatchPorts,PROOF_KEYS


def request():
    return {'cmd':'source_patch','action':'apply','request_id':'r','document_id':'1','capture_id':'1'*32,
            'ticket':'1','generation':'1','recipe_document_id':'doc','recipe_revision':'1',
            'polygon':[[.2,.2],[.4,.2],[.4,.4]],'offset':[.1,0.]}


def test_dispatch_routes_repair_capture_without_stealing_masks():
    engine=SimpleNamespace()
    assert C.handles(engine,'source_patch_capture',{'action':'arm'})
    assert not C.handles(engine,'source_patch_capture',{'action':'arm','purpose':'local-masks'})
    engine._source_patch_owner=SimpleNamespace(capture=SimpleNamespace(capture={'descriptor':{'domain':'source-input'}}))
    assert not C.handles(engine,'source_patch_capture',{'action':'presented'})
    engine._source_patch_owner.capture.capture['descriptor']['domain']='repair-input'
    assert C.handles(engine,'source_patch_capture',{'action':'presented'})


def test_exact_receipt_survives_consumed_capture_but_not_changed_request():
    p=request();owner=SourcePatchController(None,lambda e:None)
    owner.cache['r']=(owner._digest(p),{'success':True})
    engine=SimpleNamespace(_source_patch_controller=lambda:owner)
    C.require_command(engine,'source_patch',p)
    with pytest.raises(ValueError,match='different content'):
        C.require_command(engine,'source_patch',{**p,'offset':[.2,0.]})


def test_apply_requires_presented_source_and_stack(monkeypatch):
    capture={'eligible':False};calls=[]
    owner=SimpleNamespace(cache={},capture=SimpleNamespace(_matching=lambda *a,**k:capture))
    engine=SimpleNamespace(_source_patch_controller=lambda:owner)
    monkeypatch.setattr(C,'capture_binding',lambda e,c:calls.append(c))
    with pytest.raises(ValueError,match='Present'):C.require_command(engine,'source_patch',request())
    capture['eligible']=True;C.require_command(engine,'source_patch',request())
    assert len(calls)==2
    with pytest.raises(ValueError):C.require_command(engine,'source_patch',{**request(),'source_binding':{}})


def test_prepare_keeps_internal_proof_without_borrowing():
    p=request();source={'sha256':'a'*64,'width':8,'height':8}
    proof={**{k:p[k] for k in PROOF_KEYS},'kind':'source_patch','params':{'version':'source-patch-v1','polygon':p['polygon'],'offset':p['offset']},
           'weight':np.ones((8,8),np.uint8),'source_binding':source,'repair_stack_sha256':'b'*64,'repair_pixels_sha256':'c'*64}
    owner=SourcePatchController(SourcePatchPorts(lambda:None,lambda:'1',lambda p:proof,lambda p:None,lambda:{},lambda:False),lambda e:None)
    assert owner.prepare(p)
    frozen=owner.pending['proof'];source['sha256']='f'*64;proof['weight'][0,0]=0
    assert frozen['source_binding']['sha256']=='a'*64 and frozen['weight'][0,0]==1
    assert frozen['repair_stack_sha256']=='b'*64 and frozen['repair_pixels_sha256']=='c'*64


def test_commit_proof_rejects_source_stack_or_pixels_changed(monkeypatch):
    source={'sha256':'a'*64,'width':8,'height':8};engine=SimpleNamespace(_vram=SimpleNamespace(base=lambda:None))
    monkeypatch.setattr(D,'record',lambda e:{'id':'derived'})
    monkeypatch.setattr(D,'binding',lambda e:source)
    monkeypatch.setattr(C,'_stack',lambda e:'b'*64)
    monkeypatch.setattr(C,'_pixels_hash',lambda p:'c'*64)
    proof={'source_binding':deepcopy(source),'repair_stack_sha256':'b'*64,'repair_pixels_sha256':'c'*64}
    C.verify_state(engine,proof)
    for key,value in [('source_binding',None),('repair_stack_sha256','d'*64),('repair_pixels_sha256','e'*64)]:
        with pytest.raises(ValueError):C.verify_state(engine,{**proof,key:value})
    monkeypatch.setattr(D,'record',lambda e:None)
    with pytest.raises(ValueError):C.verify_state(engine,proof)


def test_capture_cancel_is_exact_and_does_not_bless_state():
    engine=SimpleNamespace()
    p={'cmd':'source_patch_capture','action':'cancel','capture_id':'1'*32,'ticket':'1','document_id':'1'}
    C.require_command(engine,'source_patch_capture',p)
    with pytest.raises(ValueError):C.require_command(engine,'source_patch_capture',{**p,'path':'original'})
    with pytest.raises(ValueError):C.require_command(engine,'source_patch_capture',{**p,'generation':True})
