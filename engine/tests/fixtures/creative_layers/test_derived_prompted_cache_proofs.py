"""AUTHORED / UNRUN: independently pinned immutable arm/SAM cache evidence.

No model, native source conversion, inference, image-quality or export acceptance
is established. The canonical conversion owner is replaced by a unit stub here.
No tests or imports were executed while authoring these fixtures.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_arm_input as A
from lumaretouch_engine import creative_derived_prompted as Q
from lumaretouch_engine import creative_derived_source as D
from lumaretouch_engine import creative_document_base as B
from lumaretouch_engine import creative_document_host as H


SOURCE={'sha256':'1'*64,'width':8,'height':6}


def owner(monkeypatch):
    engine=SimpleNamespace()
    record={'id':'sha256:'+SOURCE['sha256'],'width':8,'height':6}
    pixels=np.full((6,8,3),.4,np.float32)
    monkeypatch.setattr(D,'record',lambda current:record)
    monkeypatch.setattr(D,'binding',lambda current:deepcopy(SOURCE))
    monkeypatch.setattr(H,'memory_budget',lambda:64_000_000)
    monkeypatch.setattr(B,'export_source',lambda current,**kwargs:pixels)
    return engine,pixels


def test_canonical_creation_freezes_separate_descriptor_and_bytes_identity(monkeypatch):
    engine,_=owner(monkeypatch);packet=Q.capture(engine)
    cache=engine._creative_arm_model_input
    assert type(cache) is tuple and len(cache)==3
    assert cache[0]==('sha256:'+SOURCE['sha256'],A.TRANSFORM)
    assert cache[2]==A._packet_identity(cache[1],SOURCE)
    assert cache[2]==A._packet_identity(packet,SOURCE)
    assert type(cache[1]['pixels']) is bytes
    assert packet['descriptor'] is not cache[1]['descriptor']


def test_unchanged_capture_reuses_owned_bytes_without_decoding_full_source(monkeypatch):
    engine,_=owner(monkeypatch);packet=A.capture(engine)
    def forbidden(*args,**kwargs):raise AssertionError('Unchanged canonical input must use its bounded cache')
    monkeypatch.setattr(B,'export_source',forbidden)
    assert Q.capture(engine)==packet
    # The caller receives a descriptor copy, never the cache's mutable metadata.
    packet['descriptor']['source']['sha256']='2'*64
    assert Q.capture(engine)['descriptor']['source']==SOURCE


def test_coherent_cached_packet_replacement_cannot_claim_unchanged_source(monkeypatch):
    engine,pixels=owner(monkeypatch);A.capture(engine)
    key,cached,pinned=engine._creative_arm_model_input
    image,digest=A.inference_image(pixels+.1);data=image.tobytes(order='C')
    replacement=deepcopy(cached);replacement['pixels']=data
    replacement['descriptor']['bytes_sha256']=sha256(data).hexdigest()
    replacement['descriptor']['input_sha256']=digest
    # The packet is internally valid and still names the same source. That is
    # insufficient evidence that canonical source conversion produced it.
    A.decode(replacement['descriptor'],replacement['pixels'],SOURCE)
    engine._creative_arm_model_input=(key,replacement,pinned)
    with pytest.raises(ValueError,match='changed after canonical capture'):Q.capture(engine)


@pytest.mark.parametrize('target',['bytes','source','transform','input_sha256','extra'])
def test_cached_bytes_and_descriptor_mutations_are_rejected(monkeypatch,target):
    engine,_=owner(monkeypatch);A.capture(engine)
    key,packet,pinned=engine._creative_arm_model_input;packet=deepcopy(packet)
    if target=='bytes':packet['pixels']=b'changed'
    elif target=='source':packet['descriptor']['source']['sha256']='2'*64
    elif target=='transform':packet['descriptor']['transform']='different-transform'
    elif target=='extra':packet['unexpected']=True
    else:packet['descriptor']['input_sha256']='2'*64
    engine._creative_arm_model_input=(key,packet,pinned)
    with pytest.raises(ValueError):Q.capture(engine)


@pytest.mark.parametrize('kind',['legacy','list','empty','missing_hash','invalid_hash','boolean_hash','bad_key'])
def test_malformed_or_legacy_cache_never_gets_reblessed(monkeypatch,kind):
    engine,_=owner(monkeypatch);A.capture(engine)
    key,packet,pinned=engine._creative_arm_model_input
    malformed={'legacy':(key,packet),'list':[key,packet,pinned],'empty':(),
        'missing_hash':(key,packet,None),'invalid_hash':(key,packet,'z'*64),
        'boolean_hash':(key,packet,True),'bad_key':('not-a-key',packet,pinned)}
    engine._creative_arm_model_input=malformed[kind]
    def forbidden(*args,**kwargs):raise AssertionError('Malformed evidence must fail closed, not be silently replaced')
    monkeypatch.setattr(B,'export_source',forbidden)
    with pytest.raises(ValueError,match='captured identity'):Q.capture(engine)


def test_cache_reuse_still_verifies_current_canonical_source(monkeypatch):
    engine,_=owner(monkeypatch);A.capture(engine)
    def changed(*args,**kwargs):raise ValueError('Canonical creative source changed')
    monkeypatch.setattr(D,'verify',changed)
    with pytest.raises(ValueError,match='source changed'):Q.capture(engine)
