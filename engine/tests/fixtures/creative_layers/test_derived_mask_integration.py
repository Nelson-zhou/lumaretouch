"""AUTHORED / UNRUN: dispatch ownership, not runtime acceptance."""
from types import SimpleNamespace
import pytest
from lumaretouch_engine import creative_document_host as H
from lumaretouch_engine import creative_derived_mask_commands as M
from lumaretouch_engine import creative_derived_recovery as R


def test_global_grade_is_not_routed_to_mask_envelope(monkeypatch):
    engine=SimpleNamespace(_creative_base={'present':True},_docs=[])
    def forbidden(*args):raise AssertionError('Global grade reached mask owner')
    monkeypatch.setattr(M,'require_command',forbidden)
    H.guard_command(engine,'grade',{'cmd':'grade','action':'set','grade':[.1,0,0,1]})
    with pytest.raises(ValueError):H.guard_command(engine,'grade',{'cmd':'grade','action':'scope','scope':'skin'})


def test_mask_and_face_recovery_keep_distinct_admission(monkeypatch):
    engine=SimpleNamespace(_creative_base={'present':True},_docs=[]);calls=[]
    monkeypatch.setattr(M,'require_command',lambda *args:calls.append(('mask',args[1])))
    monkeypatch.setattr(R,'require_command',lambda *args:calls.append(('face-recovery',args[1])))
    for name,request in [('source_patch_capture',{'purpose':'local-masks'}),('local_masks',{}),('prompted_masks',{}),('local_grade_live',{}),('grade',{'action':'scope','scope':'objects'}),('effect_recovery',{})]:
        H.guard_command(engine,name,request)
    assert calls==[('mask','source_patch_capture'),('mask','local_masks'),('mask','prompted_masks'),('mask','local_grade_live'),('mask','grade'),('face-recovery','effect_recovery')]


def test_repairs_and_shared_planners_remain_fenced():
    engine=SimpleNamespace(_creative_base={'present':True},_docs=[{'state':{'_creative_base':{'present':True}}}])
    for name in ('source_patch','clone_stamp','inpaint','light','batch'):
        with pytest.raises(ValueError):H.guard_command(engine,name,{'action':'apply'})
