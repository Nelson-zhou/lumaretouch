# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. No runtime, numerical or photo-quality evidence."""
from copy import deepcopy
from pathlib import Path
import ast
import pytest
from lumaretouch_engine import face_decoration_scope as D
from lumaretouch_engine import preset_portrait_review as P
from lumaretouch_engine import face_decoration_preset_review as R
from lumaretouch_engine import face_decoration_preset_store as STORE
from lumaretouch_engine import face_decoration_preset_admission as ADMIT


def test_selected_neutral_still_requires_visual_owner():
    family=P.select({D.OP:{'recipe':D.S.neutral()}},state={})
    assert family.name=='face_decoration' and family.ack=='face_decoration_preset_ack'


def test_retained_other_face_cannot_bypass_unrelated_preset():
    family=P.select({},state={'_face_decoration_preset_retained_active':True})
    assert family.name=='face_decoration'
    assert P.select({},state={'_face_decoration_preset_retained_active':False}) is None
    assert P.select({},state={'_face_decoration_preset_retained_active':'true'}) is None


def test_selected_family_conflict_is_explicit_not_silent_module_drop():
    from lumaretouch_engine import collarbone_scope as C
    with pytest.raises(ValueError,match='distinct complete review owners'):
        P.select({C.OP:{}},state={'_face_decoration_preset_retained_active':True})


def test_read_only_envelope_never_authorizes_apply_or_ack():
    request={'cmd':'preset','action':'preflight','request_id':'read','id':'stored','document_id':'load','module_scope':['lnx.exposure.v1']}
    assert STORE.read_only(request)
    assert not STORE.read_only({**request,'action':'apply'})
    assert not STORE.read_only({**request,'face_decoration_preset_ack':{}})
    assert not STORE.read_only({**request,'module_scope':['same','same']})
    assert not STORE.read_only({**request,'eye_bag_replace_legacy':True})


def test_ack_exact_and_no_support_payload():
    ack={'document_id':'doc','revision':'7',**{key:'a'*64 for key in ('before_sha256','after_sha256','coverage_sha256','preset_sha256','applies_sha256')}}
    assert R.checked_ack(ack)==ack
    with pytest.raises(ValueError):R.checked_ack({**ack,'support':{}})
    with pytest.raises(ValueError):R.checked_ack({**ack,'revision':7})


def test_candidate_changes_only_scalar_intent(monkeypatch):
    recipe={**D.S.neutral(),'strength':.4}
    state={D.FIELD:D.S.neutral(),'source':object(),'support':{'target':'own'},'repair':['retained']}
    monkeypatch.setattr(ADMIT,'require_modules',lambda state,modules,**kw:deepcopy(modules))
    result=ADMIT.candidate(state,{D.OP:{'recipe':recipe}})
    assert result[D.FIELD]==recipe and result[D.REQUESTED] is True
    assert result['source'] is state['source'] and result['support'] is state['support']
    assert result['repair'] is state['repair'] and state[D.FIELD]==D.S.neutral()


def test_controller_all_select_calls_bind_current_state_source_contract():
    path=Path(__file__).parents[1]/'src/lumaretouch_engine/preset_controller.py'
    tree=ast.parse(path.read_text())
    calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
        and isinstance(node.func.value,ast.Name) and node.func.value.id=='PORTRAIT' and node.func.attr=='select']
    assert calls and all(any(kw.arg=='state' for kw in node.keywords) for node in calls)
    source=path.read_text()
    assert 'verify_face_decoration=self.ports.verify_face_decoration' in source
    assert "face_decoration_preset_ack" in source


def test_expired_failure_echo_retains_companion_identity_without_authority():
    ack={'document_id':'doc','revision':'7',**{key:'a'*64 for key in ('before_sha256','after_sha256','coverage_sha256','preset_sha256','applies_sha256')}}
    request={'id':'preset','document_id':'load','preflight_token':'expired','face_decoration_preset_ack':ack,
        'spill_review_ack':[{'document_id':'doc','revision':'7','before_sha256':'b'*64,'after_sha256':'c'*64}]}
    echo=R.failure_echo(request)
    assert echo['spill_review_ack']==request['spill_review_ack']
    assert echo['face_decoration_visual_required'] is True and 'success' not in echo and 'module_scope' not in echo
    with pytest.raises(ValueError):R.failure_echo({**request,'shadow_review_ack':{'huge':'x'*257}})
