"""AUTHORED / UNRUN: effective source identity and inference ownership."""
import struct
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine.creative_document_assets import make_asset
from lumaretouch_engine import creative_derived_source as D


def source(value=.5):
    return make_asset('rgba',1,1,struct.pack('<ffff',value,.25,.125,1.))


def test_identity_is_canonical_pixels_not_original_path():
    first,second = source(.5),source(.50001)
    a = D.binding({'_creative_base':first},'/same/original.jpg')
    b = D.binding({'_creative_base':second},'/same/original.jpg')
    assert a != b
    assert a == {'sha256':first['id'][7:],'width':1,'height':1}
    assert D.binding({'creative_base':deepcopy(first)}) == a


def test_original_precompute_cannot_be_relabelled_as_composite():
    pc = SimpleNamespace(input_source_binding=None,masks={})
    with pytest.raises(ValueError): D.verify_precompute({'_creative_base':source()},pc)


def test_derived_precompute_proof_survives_owned_snapshot_and_rejects_another_base(monkeypatch):
    first,second = source(),source(.6)
    engine = SimpleNamespace(_creative_base=first)
    rgb = np.array([[[188,137,99]]],dtype=np.uint8);rgb.setflags(write=False)
    monkeypatch.setattr(D,'analysis_rgb',lambda _:rgb)
    pc = SimpleNamespace(masks={'skin':np.ones((1,1),np.float32)})
    D.stamp_precompute(engine,pc,rgb)
    D.verify_precompute(engine,pc)
    D.verify_precompute({'_creative_base':first},deepcopy(pc))
    with pytest.raises(ValueError): D.verify_precompute({'_creative_base':second},pc)
    with pytest.raises(ValueError): D.verify_precompute({'_creative_base':None},pc)
    assert pc.input_source_binding['proxy_sha256'] != first['id'][7:]


def test_changed_analysis_proxy_fails_live_replay(monkeypatch):
    engine=SimpleNamespace(_creative_base=source())
    rgb=np.array([[[188,137,99]]],np.uint8)
    pc=SimpleNamespace(masks={})
    D.stamp_precompute(engine,pc,rgb)
    monkeypatch.setattr(D,'analysis_rgb',lambda _:np.zeros((1,1,3),np.uint8))
    with pytest.raises(ValueError):D.verify_precompute(engine,pc)


def test_only_local_analysis_cursor_actions_bypass_cross_document_fence():
    from lumaretouch_engine.creative_document_host import guard_command
    engine=SimpleNamespace(_creative_base=source(),_docs=[{'state':{'_creative_base':source()}}])
    for action in ('select','target','analyse_face'):
        guard_command(engine,'people',{'action':action,'target':{'scope':'face'}})
    for action in ('patch','link','iris_review'):
        with pytest.raises(ValueError):guard_command(engine,'people',{'action':action,'target':{'scope':'face'}})
    with pytest.raises(ValueError):guard_command(engine,'people',{'action':'target','target':{'scope':'group'}})
