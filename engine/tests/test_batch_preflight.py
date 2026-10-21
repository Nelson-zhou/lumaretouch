from dataclasses import FrozenInstanceError
import pytest
from lumaretouch_engine.batch_preflight import PreflightStore,FrozenTarget,TTL_NS,MAX_PENDING


def fixture():
    clock=[1];store=PreflightStore(lambda:clock[0])
    def create(params=None):
        return store.create('workspace','source',1,'/source',['ev'],params or {'ev':{'value':1}},'skip_and_report',
            [FrozenTarget('target',2,0,'/target',None,'{"ev":0}')],[])
    return store,clock,create


def test_source_parameters_and_target_records_are_immutable_detached_values():
    store,_,create=fixture();source={'ev':{'value':1}};plan=create(source);source['ev']['value']=9
    assert plan.params()=={'ev':{'value':1}}
    copy=plan.params();copy['ev']['value']=8;assert plan.params()['ev']['value']==1
    with pytest.raises(FrozenInstanceError):plan.source_revision=9
    with pytest.raises(FrozenInstanceError):plan.targets[0].revision=9


def test_workspace_expiry_and_bounded_pending_records():
    store,clock,create=fixture();plan=create()
    with pytest.raises(ValueError):store.get(plan.token,'another')
    clock[0]+=TTL_NS
    with pytest.raises(ValueError):store.get(plan.token,'workspace')
    plans=[create() for _ in range(MAX_PENDING+1)]
    assert len(store.pending)==MAX_PENDING
    with pytest.raises(ValueError):store.get(plans[0].token,'workspace')


def test_terminal_results_are_detached_and_do_not_reopen_consumed_plan():
    store,_,create=fixture();plan=create();result={'success':True,'batch_id':'b1'}
    store.finish(plan,result);result['success']=False
    assert store.completed(plan.token,'workspace')=={'success':True,'batch_id':'b1'}
    with pytest.raises(ValueError):store.get(plan.token,'workspace')
    with pytest.raises(ValueError):store.completed(plan.token,'another')


def test_unencodable_receipt_keeps_token_consumed_with_unknown_outcome(monkeypatch):
    import lumaretouch_engine.batch_preflight as module
    store,_,create=fixture();plan=create();store.claim(plan)
    monkeypatch.setattr(module,'MAX_RESULT_BYTES',1)
    result=store.finish(plan,{'success':True,'batch_id':'applied'})
    assert not result['success'] and result['outcome_unknown']
    assert store.completed(plan.token,'workspace')['outcome_unknown']
    with pytest.raises(ValueError):store.get(plan.token,'workspace')
