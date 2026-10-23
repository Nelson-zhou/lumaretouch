"""AUTHORED / UNRUN: durable source stacks, not photographic acceptance."""
from copy import deepcopy
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_repairs as D, project as P
from lumaretouch_engine.repair_record import RepairOp, check_repair_fields
from test_derived_effects_contract import fixture


def op(source=None,identity=1):
    return RepairOp(identity,np.ones((4,4),np.uint8),
        {'version':'source-patch-v1','polygon':[[.1,.1],[.5,.1],[.3,.5]],'offset':[.1,.1]},
        'source_patch',deepcopy(source))


def test_legacy_original_and_exact_derived_stacks(monkeypatch):
    engine,_,_,source,_=fixture(monkeypatch)
    D.validate_stacks({'_repair_ops':[op()]})
    engine._repair_ops=[op(source)];engine._redo_ops=[op(source,2)]
    assert D.validate_stacks(engine)==source
    for bad in (None,{**source,'sha256':'f'*64},{**source,'width':8}):
        engine._redo_ops=[op(bad)]
        with pytest.raises(ValueError):D.validate_stacks(engine)
    with pytest.raises(ValueError):D.validate_stacks({'repair_ops':[op(source)]})


def test_binding_shape_and_heal_are_not_coerced():
    for bad in ({'sha256':'a'*64,'width':True,'height':4},{'sha256':'A'*64,'width':4,'height':4},{}):
        with pytest.raises(ValueError):D.check_binding(bad)
    source={'sha256':'a'*64,'width':4,'height':4}
    heal=RepairOp(1,np.ones((4,4),np.uint8),{},'heal',source)
    with pytest.raises(ValueError):D.validate_source_ops([heal],source)
    assert check_repair_fields({'op_id':1,'weight':heal.weight,'params':{}})['source_binding'] is None


def test_digest_tracks_order_pixels_params_redo_and_source():
    source={'sha256':'a'*64,'width':4,'height':4};a=op(source);b=op(source,2)
    first=D.digest_ops([a,b],[],source)
    assert first!=D.digest_ops([b,a],[],source)
    assert first!=D.digest_ops([a],[b],source)
    changed=deepcopy(a);changed.weight[0,0]=2
    assert first!=D.digest_ops([changed,b],[],source)
    changed=deepcopy(a);changed.params['offset'][0]=.2
    assert first!=D.digest_ops([changed,b],[],source)
    other={**source,'sha256':'b'*64}
    assert first!=D.digest_ops([op(other),op(other,2)],[],other)


def test_encode_decode_preserves_binding_and_rejects_foreign_redo(monkeypatch):
    engine,_,_,source,_=fixture(monkeypatch)
    state={'_creative_base':engine._creative_base,'_repair_ops':[op(source)],'_redo_ops':[]}
    assets={};dropped=[];encoded=P.encode(state,assets,dropped,'state')
    restored=P.decode(encoded,assets,dropped,'state')
    assert restored['_repair_ops'][0].source_binding==source and not dropped
    assert D.stack_digest(restored)==D.stack_digest(state)
    encoded['_redo_ops']=[deepcopy(encoded['_repair_ops'][0])]
    encoded['_redo_ops'][0]['fields']['source_binding']['sha256']='f'*64
    with pytest.raises(ValueError):P.decode(encoded,assets,[],'state')
    bad=deepcopy(state);bad['_repair_ops'][0].source_binding=None
    with pytest.raises(ValueError):P.encode(bad,{},[],'state')


def test_inactive_frames_and_aliases_cannot_hide_foreign_source(monkeypatch):
    engine,_,_,source,_=fixture(monkeypatch)
    state={'_creative_base':engine._creative_base,'_repair_ops':[op(source)],'_redo_ops':[]}
    wrong=deepcopy(state);wrong['_repair_ops'][0].source_binding['sha256']='f'*64
    with pytest.raises(ValueError):P.encode({'undo':[state,wrong]}, {}, [], 'history')
    with pytest.raises(ValueError):D.validate_stacks({**state,'repair_ops':[]})
