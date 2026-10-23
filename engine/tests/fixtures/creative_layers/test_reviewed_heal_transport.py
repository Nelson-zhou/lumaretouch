"""AUTHORED / UNRUN: reviewed heal envelope/receipt/ownership contracts."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_repair_commands as C
from lumaretouch_engine import source_patch_controller as P
from test_derived_repair_commands import request


def heal_request():
    p=request();p.pop('polygon');p.pop('offset')
    return {**p,'kind':'heal_vector','stroke':{'points':[[.5,.5]],'size':.1,'hardness':.6,'opacity':1.}}


def test_heal_uses_exact_reviewed_receipt_transport():
    p=heal_request();owner=P.SourcePatchController(None,lambda event:None)
    owner.cache[p['request_id']]=(owner._digest(p),{'success':True,'kind':'heal_vector'})
    engine=SimpleNamespace(_source_patch_controller=lambda:owner)
    C.require_command(engine,'source_patch',p)
    changed=deepcopy(p);changed['stroke']['size']=.2
    with pytest.raises(ValueError,match='different content'):C.require_command(engine,'source_patch',changed)
    for extra in ({'rle':[]},{'polygon':[]},{'offset':[0,0]},{'source_binding':{}}):
        with pytest.raises(ValueError):C.require_command(engine,'source_patch',{**p,**extra})


def test_heal_requires_presented_capture(monkeypatch):
    p=heal_request();capture={'eligible':False};seen=[]
    owner=SimpleNamespace(cache={},capture=SimpleNamespace(_matching=lambda *a,**k:capture))
    engine=SimpleNamespace(_source_patch_controller=lambda:owner)
    monkeypatch.setattr(C,'capture_binding',lambda e,c:seen.append(c))
    with pytest.raises(ValueError,match='Present'):C.require_command(engine,'source_patch',p)
    capture['eligible']=True;C.require_command(engine,'source_patch',p)
    assert len(seen)==2


def test_controller_keeps_heal_proof_without_offset_or_borrowed_pixels(monkeypatch):
    p=heal_request();binding={'sha256':'a'*64,'width':8,'height':8}
    proof={**{k:p[k] for k in P.PROOF_KEYS},'kind':'heal_vector','params':{'opacity':1.},
        'weight':np.ones((8,8),np.uint8),'source_binding':binding,
        'repair_stack_sha256':'b'*64,'repair_pixels_sha256':'c'*64}
    # Geometry/solver validation belongs to its dedicated fixture; this probes
    # transport copying and ensures heal is not mistaken for a zero-offset clone.
    monkeypatch.setattr(P,'check_repair_fields',lambda fields:deepcopy(fields))
    owner=P.SourcePatchController(P.SourcePatchPorts(lambda:None,lambda:'1',lambda p:proof,lambda p:None,lambda:{},lambda:False),lambda e:None)
    assert owner.prepare(p)
    retained=owner.pending['proof'];binding['sha256']='f'*64;proof['weight'][0,0]=0
    assert retained['kind']=='heal_vector' and retained['source_binding']['sha256']=='a'*64
    assert retained['weight'][0,0]==1 and retained['repair_stack_sha256']=='b'*64
    assert owner.pending['result']['kind']=='heal_vector'


def test_zero_opacity_heal_is_receipted_without_history_mutation(monkeypatch):
    p=heal_request();p['stroke']['opacity']=0.
    proof={**{k:p[k] for k in P.PROOF_KEYS},'kind':'heal_vector','params':{'opacity':0.},
        'weight':np.zeros((8,8),np.uint8),'source_binding':None}
    monkeypatch.setattr(P,'check_repair_fields',lambda fields:deepcopy(fields))
    owner=P.SourcePatchController(P.SourcePatchPorts(lambda:None,lambda:'1',lambda p:proof,lambda p:None,lambda:{'counts':{'repair':2}},lambda:False),lambda e:None)
    assert owner.prepare(p) is False
    assert owner.pending['proof'] is None
    result=owner.pending['result']
    assert result['success'] and result['no_change'] and result['before_count']==result['after_count']==2
