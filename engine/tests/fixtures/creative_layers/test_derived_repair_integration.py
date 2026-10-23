"""AUTHORED / UNRUN: source-switch history and dispatch ownership contracts."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import creative_document_host as H, history_policy as HP
from lumaretouch_engine import creative_derived_repair_commands as C
from lumaretouch_engine import creative_derived_mask_commands as M
from lumaretouch_engine import creative_derived_repairs as R
from test_derived_repair_records import op
from test_derived_effects_contract import fixture


def test_history_signature_covers_nonprinted_coverage_and_source(monkeypatch):
    engine,_,_,source,_=fixture(monkeypatch)
    a=op(source);a.weight=np.ones((64,64),np.uint8)
    state={'_creative_base':engine._creative_base,'_repair_ops':[a],'_redo_ops':[]}
    first=HP.state_signature(state)
    changed=deepcopy(state);changed['_repair_ops'][0].weight[31,31]=2
    assert first!=HP.state_signature(changed)
    changed=deepcopy(state);changed['_redo_ops']=changed.pop('_repair_ops');changed['_repair_ops']=[]
    assert first!=HP.state_signature(changed)
    wrong=deepcopy(state);wrong['_creative_base']=None
    with pytest.raises(ValueError):R.validate_stacks(wrong)
    # A source switch selects a whole frame, never unions original and derived ops.
    original={'_creative_base':None,'_repair_ops':[op()],'_redo_ops':[]}
    R.validate_stacks(original);R.validate_stacks(state)
    original['_redo_ops']=state['_repair_ops']
    with pytest.raises(ValueError):R.validate_stacks(original)


def test_repair_capture_routing_does_not_replace_local_mask_owner(monkeypatch):
    engine=SimpleNamespace(_creative_base={'present':True},_docs=[]);seen=[]
    monkeypatch.setattr(C,'require_command',lambda *args:seen.append('repair'))
    monkeypatch.setattr(M,'require_command',lambda *args:seen.append('mask'))
    H.guard_command(engine,'source_patch_capture',{'cmd':'source_patch_capture','action':'arm','purpose':'repair'})
    H.guard_command(engine,'source_patch_capture',{'cmd':'source_patch_capture','action':'arm','purpose':'local-masks'})
    H.guard_command(engine,'clone_stamp',{'cmd':'clone_stamp','action':'apply'})
    assert seen==['repair','mask','repair']
    for name in ('inpaint','light','batch'):
        with pytest.raises(ValueError):H.guard_command(engine,name,{'cmd':name,'action':'apply'})
