"""AUTHORED / UNRUN: immutable derived arm model input, not visual/native acceptance."""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_arm_input as D
from lumaretouch_engine import prompted_mask_source as P
from lumaretouch_engine import arm_shape_selection as S


def packet(pixels):
    image, digest=D.inference_image(pixels)
    data=image.tobytes()
    source={'sha256':'a'*64,'width':pixels.shape[1],'height':pixels.shape[0]}
    return {'descriptor':{'version':1,'source':source,'transform':D.TRANSFORM,
            'width':image.shape[1],'height':image.shape[0],
            'bytes_sha256':sha256(data).hexdigest(),'input_sha256':digest},'pixels':data}


def test_float_transform_is_model_only_and_round_half_up():
    value=np.array([[[0.,.5,1.],[.1,.2,.3]]],np.float32)
    before=value.copy();image,digest=D.inference_image(value)
    expected=np.floor(value*255+np.float32(.5)).astype(np.uint8)
    np.testing.assert_array_equal(value,before)
    np.testing.assert_array_equal(image,expected)
    assert digest==P.inference_image(expected)[1]
    assert not image.flags.writeable


@pytest.mark.parametrize('bad',[np.nan,np.inf,-.001,1.001])
def test_float_model_input_refuses_hdr_and_nonfinite(bad):
    value=np.zeros((3,4,3),np.float32);value[0,0,0]=bad
    with pytest.raises(ValueError,match='HDR'):D.inference_image(value)


def test_packet_and_full_source_replay_identical_input():
    value=np.full((8,12,3),.123456,np.float32);owned=packet(value)
    selection={'source':{**owned['descriptor']['source'],'orientation':'exif-transposed-v1'},
               'binding':{'input_sha256':owned['descriptor']['input_sha256']}}
    S.verify_input(value,selection)
    S.verify_input(owned,selection)
    stale=deepcopy(selection);stale['source']['sha256']='b'*64
    with pytest.raises(ValueError,match='another effective source'):S.verify_input(owned,stale)
    changed=dict(owned,pixels=b'\x01'+owned['pixels'][1:])
    with pytest.raises(ValueError,match='bytes changed'):S.verify_input(changed,selection)
    wrong=deepcopy(owned);wrong['descriptor']['input_sha256']='c'*64
    with pytest.raises(ValueError,match='contract hash'):S.verify_input(wrong,selection)


def test_packet_is_whole_source_transform_not_arbitrary_proxy():
    value=np.full((24,32,3),.4,np.float32);owned=packet(value)
    wrong=deepcopy(owned);wrong['descriptor']['width']=16
    with pytest.raises(ValueError,match='dimensions'):D.decode(wrong['descriptor'],wrong['pixels'],owned['descriptor']['source'])
    wrong=deepcopy(owned);wrong['descriptor']['transform']='display-matte-proxy'
    with pytest.raises(ValueError,match='transform'):D.decode(wrong['descriptor'],wrong['pixels'],owned['descriptor']['source'])


def test_capture_reuses_only_canonical_identity_and_verifies_binding(monkeypatch):
    from lumaretouch_engine import creative_derived_source as SOURCE, creative_document_base as BASE, creative_document_host as HOST
    source={'sha256':'a'*64,'width':12,'height':8};record={'id':'sha256:'+'a'*64,'width':12,'height':8}
    engine=SimpleNamespace();calls=[]
    monkeypatch.setattr(SOURCE,'record',lambda e:record)
    monkeypatch.setattr(SOURCE,'binding',lambda e:dict(source))
    monkeypatch.setattr(SOURCE,'verify',lambda expected,e: source if expected==source else (_ for _ in ()).throw(ValueError('changed')))
    monkeypatch.setattr(HOST,'memory_budget',lambda:64*1024*1024)
    def pixels(*a,**k):calls.append(record['id']);return np.full((8,12,3),.4,np.float32)
    monkeypatch.setattr(BASE,'export_source',pixels)
    first=D.capture(engine);second=D.capture(engine)
    assert len(calls)==1 and first['pixels'] is second['pixels']
    second['descriptor']['source']['sha256']='b'*64
    assert D.capture(engine)['descriptor']['source']['sha256']=='a'*64
    record['id']='sha256:'+'c'*64;source['sha256']='c'*64
    assert D.capture(engine)['descriptor']['source']['sha256']=='c'*64 and len(calls)==2
