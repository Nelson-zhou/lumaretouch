"""AUTHORED / UNRUN: effective body acquisition and command ownership.

Synthetic pose points and mocked producer outputs are contracts, not actual
inference, anatomy, native rendering, or functional/visual acceptance evidence.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import numpy as np
import pytest
from test_derived_effects_contract import fixture
from lumaretouch_engine import creative_derived_body as D, creative_derived_source as SOURCE
from lumaretouch_engine import body_pose_commands as C, body_pose_evidence as E, body_pose_state as B
from lumaretouch_engine import body_pose_render as R, arm_shape_project as P


def observed(source,rgb):
    values=[dict(index=i,x=.5,y=.5,z=0.,visibility=0.,presence=0.) for i in range(33)]
    return E.create(source_frame=R.source(source),values=values,backend_version='fixture',
        backend_code_sha256='a'*64,model_id='synthetic-unit-test-only',model_sha256='b'*64,
        input_rgb_sha256=sha256(memoryview(np.ascontiguousarray(rgb))).hexdigest(),
        input_dimensions=(rgb.shape[1],rgb.shape[0]))


def run(source,rgb):
    return dict(source=R.source(source),records=[observed(source,rgb)],detector_limit=4,
                limit_reached=False,census_complete=False)


def setup(monkeypatch,*,empty=False):
    engine,people,_,source,rgb=fixture(monkeypatch)
    bank=B.empty() if empty else B.add_run(B.empty(),run(source,rgb))
    engine._body_bank=lambda:deepcopy(bank)
    engine._src_rgb=np.zeros_like(rgb)
    return engine,people,source,rgb,bank


def message(name,action,request):
    return dict(cmd=name,request_id='outer-request',action=action,request=request)


def edit(engine,people,bank,name='shoulder_shape'):
    ref=next(iter(bank['bodies'].values()))['record']['body_ref']
    binding=engine._people_binding()
    request={k:binding[k] for k in ('document_id','document_epoch','document_revision')}
    request.update(request_id='inner-request',gesture_id='gesture',state_revision=bank['revision'],
        association_revision=bank['association_revision'],people_association_revision=people['association_revision'],
        body_ref=ref,action='operation_status',payload={'enabled':True})
    if name=='shoulder_shape':request['payload']['operation_id']='lnx.shoulder_shape.v1'
    else:
        request.update(body_graph_sha256=P.graph_digest(bank),people_graph_sha256=P.people_digest(people))
        if name=='arm_shape':
            request['family_id']='lnx.arm_shape.v1';request['payload']['segment']='left_upper'
        else:request['operation_id']='lnx.'+name+'.v1'
    return message(name,'execute' if name=='arm_shape' else 'edit',request)


@pytest.mark.parametrize('name',sorted(D.COMMANDS))
def test_exact_transport_and_native_fences(monkeypatch,name):
    engine,people,source,rgb,bank=setup(monkeypatch)
    D.require_command(engine,name,message(name,'view',{}))
    D.require_command(engine,name,message(name,'select',{'binding':engine._people_binding(),
        'body_ref':next(iter(bank['bodies'].values()))['record']['body_ref']}))
    command=edit(engine,people,bank,name)
    D.require_command(engine,name,command)
    bad=deepcopy(command);bad['request']['document_revision']+=1
    with pytest.raises(ValueError):D.require_command(engine,name,bad)
    bad=deepcopy(command);bad['request']['action']='copy_source_mask'
    with pytest.raises(ValueError):D.require_command(engine,name,bad)
    bad=deepcopy(command);bad['request']['payload']['source_path']='/original.png'
    with pytest.raises(ValueError):D.require_command(engine,name,bad)
    bad=deepcopy(command);bad['request_id']='inner-request'
    with pytest.raises(ValueError):D.require_command(engine,name,bad)


@pytest.mark.parametrize('name',sorted(D.COMMANDS-{'arm_shape'}))
def test_exact_analysis_binding(monkeypatch,name):
    engine,_,_,_,_=setup(monkeypatch,empty=True)
    request={'binding':engine._people_binding()}
    D.require_command(engine,name,message(name,'analyse',request))
    request['binding']['asset_sha256']='e'*64
    with pytest.raises(ValueError):D.require_command(engine,name,message(name,'analyse',request))


def test_arm_routes_do_not_admit_pose_analysis_or_unowned_proposal(monkeypatch):
    engine,people,_,_,bank=setup(monkeypatch)
    with pytest.raises(ValueError):D.require_command(engine,'arm_shape',message('arm_shape','analyse',{'binding':engine._people_binding()}))
    command=edit(engine,people,bank,'arm_shape');command['action']='proposal_start'
    with pytest.raises(ValueError):D.require_command(engine,'arm_shape',command)


def test_retained_exact_outer_and_inner_receipts_survive_stale_binding(monkeypatch):
    engine,people,_,_,bank=setup(monkeypatch)
    command=edit(engine,people,bank)
    engine._body_edit_owner=SimpleNamespace(receipts={'inner-request':{'digest':E.content_digest(command['request']),'result':{'phase':'done'}}})
    engine._people_binding=lambda:dict(document_id='switched',document_epoch='new',document_revision=99,asset_sha256='f'*64)
    D.require_command(engine,'shoulder_shape',command)
    changed=deepcopy(command);changed['request']['payload']['enabled']=False
    with pytest.raises(ValueError):D.require_command(engine,'shoulder_shape',changed)
    engine._body_edit_owner.receipts={}
    engine._body_transport=SimpleNamespace(seen={'outer-request':E.content_digest(command)})
    D.require_command(engine,'shoulder_shape',command)
    with pytest.raises(ValueError):D.require_command(engine,'shoulder_shape',changed)


def test_status_and_cancel_remain_query_only_after_switch():
    engine=SimpleNamespace()
    D.require_command(engine,'shoulder_shape',message('shoulder_shape','status',{'request_id':'old'}))
    for action in ('proposal_status','proposal_cancel'):
        D.require_command(engine,'arm_shape',message('arm_shape',action,{'job_id':'old-job'}))
    with pytest.raises(ValueError):D.require_command(engine,'arm_shape',message('arm_shape','proposal_status',{'job_id':'old-job','path':'/original.png'}))


def test_disabled_rows_runs_and_historical_support_cannot_leak_original_source(monkeypatch):
    _,_,source,rgb,bank=setup(monkeypatch)
    foreign={**source,'sha256':'e'*64}
    foreign_bank=B.add_run(B.empty(),run(foreign,rgb))
    next(iter(foreign_bank['bodies'].values()))['enabled']=False
    with pytest.raises(ValueError):D.validate(foreign_bank,source)
    no_rows=B.empty();no_rows['analysis_runs'][foreign['sha256']]=dict(detector_limit=4,limit_reached=False,census_complete=False)
    with pytest.raises(ValueError):D.validate(no_rows,source)
    record=observed(foreign,rgb)
    support=dict(version=1,operation_id='lnx.leg_shape.v1',body_ref=record['body_ref'],
        points_sha256=record['points_sha256'],source=record['source'],kind='historical-fixture',
        data={},data_sha256=E.content_digest({}))
    bank['support_assets'][E.content_digest(support)]=support
    with pytest.raises(ValueError):D.validate(bank,source)


def test_unknown_disabled_body_operation_is_not_a_guard_bypass(monkeypatch):
    _,_,source,_,bank=setup(monkeypatch)
    next(iter(bank['bodies'].values()))['operations']['lnx.future.v1']=dict(enabled=False,recipe={'version':1},review=None,support_sha256=None)
    with pytest.raises(ValueError):D.validate(bank,source)


def acquisition(monkeypatch,*,original=False,change=None):
    from lumaretouch_engine import body_pose_runtime as runtime, cpu_memory_budget as budget
    engine,_,source,rgb,_=setup(monkeypatch,empty=True)
    if original:
        engine._creative_base=None
        monkeypatch.setattr(SOURCE,'binding',lambda *args,**kwargs:deepcopy(source))
        monkeypatch.setattr(SOURCE,'analysis_rgb',lambda _:engine._src_rgb)
    expected=engine._src_rgb if original else rgb
    seen=[];published=[]
    engine._guard_editable=lambda _:None;engine._people_bind=lambda:None
    engine._cancel_snapshot=lambda _:None;engine._close_owned_previews=lambda:None
    def producer(pixels,frame,**kwargs):
        assert not pixels.flags.writeable
        np.testing.assert_array_equal(pixels,expected)
        assert not np.shares_memory(pixels,expected)
        seen.append(pixels.copy());result=run(source,pixels)
        if change is not None:change(engine,result)
        return result
    monkeypatch.setattr(runtime,'analyse',producer)
    monkeypatch.setattr(budget,'available_estimate',lambda:256*1024*1024)
    monkeypatch.setattr(C,'commit_observations',lambda e,bank,*a:published.append(bank))
    monkeypatch.setattr(C,'response',lambda e,**kwargs:{'preview':kwargs.get('preview',False)})
    command=message('shoulder_shape','analyse',{'binding':engine._people_binding()})
    return engine,command,seen,published


@pytest.mark.parametrize('original',[False,True])
def test_actual_analyse_success_uses_effective_pixels_and_response_closure(monkeypatch,original):
    engine,command,seen,published=acquisition(monkeypatch,original=original)
    assert C.apply(engine,command)=={'preview':True}
    assert len(seen)==1 and len(published)==1
    assert engine._body_candidates is None


@pytest.mark.parametrize('change',[
    lambda e,r:r['records'][0].update(input_rgb_sha256='f'*64),
    lambda e,r:r['records'][0].update(input_dimensions=[8,8]),
    lambda e,r:r['source'].update(sha256='f'*64),
    lambda e,r:setattr(e,'_people_binding',lambda:dict(document_id='switched')),
    lambda e,r:e._creative_base.update(id='sha256:'+'f'*64),
])
def test_acquisition_mismatch_never_publishes(monkeypatch,change):
    engine,command,_,published=acquisition(monkeypatch,change=change)
    with pytest.raises((ValueError,KeyError)):C.apply(engine,command)
    assert published==[]


def test_changed_current_analysis_pixels_never_publish(monkeypatch):
    engine,command,_,published=acquisition(monkeypatch,
        change=lambda e,r:monkeypatch.setattr(SOURCE,'analysis_rgb',lambda _:np.zeros((4,4,3),np.uint8)))
    with pytest.raises(ValueError):C.apply(engine,command)
    assert published==[]
