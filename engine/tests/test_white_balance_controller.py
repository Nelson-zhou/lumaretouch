from copy import deepcopy
import json
import pytest
from lumaretouch_engine.white_balance_controller import WhiteBalanceController,WhiteBalancePorts
from lumaretouch_engine import white_balance_recipe as W


def fixture(apply_result=True):
    exposure={'ev':1.,'temperature_shift':500.,'tint_shift':.2,'contrast':10.,'highlights':20.,'shadows':30.,'saturation':40.,'reference_k':None,'lit':True,'options':W.default_options()}
    events=[];calls=[];history={'undo_steps':0,'redo_steps':0};reload=[False]
    def apply(patch):
        calls.append(deepcopy(patch))
        if apply_result is True:
            exposure['options']=deepcopy(patch['wb_options'])
            for key in ('temperature_shift','tint_shift'):
                if key in patch:exposure[key]=patch[key]
        return apply_result
    ports=WhiteBalancePorts(lambda:None,lambda:'doc',lambda:{'document_id':'doc','exposure':deepcopy(exposure),'history':dict(history)},apply,lambda:reload[0])
    c=WhiteBalanceController(ports,events.append)
    return c,exposure,events,calls,history,reload


def request(action='reset',rid='r',**kw):return {'cmd':'white_balance','request_id':rid,'document_id':'doc','action':action,**kw}


def test_reset_preserves_non_wb_fields_and_receipt_waits_for_history():
    c,state,events,calls,history,_=fixture();before=deepcopy(state);p=request()
    c.handle(p);assert not any(e['event']=='white_balance_result' for e in events)
    history['undo_steps']=1;c.finish(p);r=events[-1]
    assert r['success'] and r['history']['undo_steps']==1 and len(calls)==1
    for key in ('ev','contrast','highlights','shadows','saturation','reference_k'):assert state[key]==before[key]
    assert state['temperature_shift']==state['tint_shift']==0 and state['options']['algorithm']==W.LEGACY


def test_algorithm_switch_preserves_manual_picks_and_reference():
    c,state,events,_,_,_=fixture();state['options']['picked_gains']=[1.2,.8,1.1];before=deepcopy(state)
    p=request('set_algorithm',algorithm=W.CORRECTED);c.handle(p);c.finish(p)
    assert events[-1]['success'] and state['options']['algorithm']==W.CORRECTED
    assert state['options']['picked_gains']==before['options']['picked_gains']
    assert state['temperature_shift']==500 and state['tint_shift']==.2 and state['reference_k'] is None


def test_transaction_rejection_is_not_success_and_failed_rollback_is_unknown():
    c,_,events,_,_,reload=fixture(False);p=request();c.handle(p);c.finish(p)
    assert not events[-1]['success'] and not events[-1]['outcome_unknown']
    reload[0]=True;p=request(rid='r2');c.handle(p);c.finish(p)
    assert events[-1]['outcome_unknown'] and events[-1]['requires_reload']


def test_history_failure_cannot_be_reported_as_completed():
    c,_,events,_,_,_=fixture();p=request();c.handle(p);c.finish(p,'history failed')
    assert not events[-1]['success'] and events[-1]['outcome_unknown']


def test_replay_and_noop_never_reapply_and_reused_identity_rejects():
    c,_,events,calls,_,_=fixture();p=request();c.handle(p);c.finish(p)
    c.handle(p);c.finish(p);assert events[-1]['replayed'] and len(calls)==1
    p=request(rid='new');c.handle(p);c.finish(p);assert events[-1]['no_change'] and len(calls)==1
    p=request('set_algorithm',rid='r',algorithm=W.CORRECTED);c.handle(p);c.finish(p)
    assert not events[-1]['success'] and len(calls)==1


def test_stale_document_and_invalid_algorithm_never_apply():
    c,_,events,calls,_,_=fixture()
    for p in (request(document_id='old'),request('set_algorithm',algorithm='unknown')):
        c.handle(p);c.finish(p);assert not events[-1]['success']
    assert not calls


def test_invalid_unicode_and_large_identity_have_bounded_terminal_failures():
    c,_,events,calls,_,_=fixture()
    for p in (request(rid='\ud800'),request(document_id='x'*100000),request(action='x'*100000)):
        c.handle(p);c.finish(p)
        assert not events[-1]['success'] and len(json.dumps(events[-1]).encode())<16384
    assert not calls and not c.cache


def test_cache_eviction_is_bounded():
    c,_,events,_,_,_=fixture()
    for i in range(70):
        p=request(rid=str(i));c.handle(p);c.finish(p)
    assert len(c.cache)==64 and '0' not in c.cache
