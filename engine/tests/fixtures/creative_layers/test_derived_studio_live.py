"""AUTHORED / UNRUN: derived studio live source, async and receipt contracts.

Synthetic tensors/jobs below do not execute models, native masks, rendering or
the product. These fixtures are not evidence of visual or runtime acceptance.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import numpy as np
import pytest
from lumaretouch_engine import studio_background_state as S,studio_background_preview as P
from lumaretouch_engine import studio_background_runtime as R,creative_studio_host as H
from lumaretouch_engine import creative_derived_source as D,creative_derived_studio as C
from lumaretouch_engine import local_mask_state as M


SOURCE={'sha256':'a'*64,'width':8,'height':6}


class Tensor:
    def __init__(self,array):
        self.array=array;self.shape=array.shape;self.dtype=array.dtype;self.device='cpu';self._version=0
    def __getitem__(self,key):return Tensor(self.array[key])
    def permute(self,*axes):return Tensor(self.array.transpose(axes))
    def detach(self):return self
    def cpu(self):return self
    def numpy(self):return self.array
    def data_ptr(self):return self.array.__array_interface__['data'][0]


class Future:
    def __init__(self,function,args):self.function,self.args=function,args;self.finished=False
    def complete(self):self.value=self.function(*self.args);self.finished=True
    def done(self):return self.finished
    def result(self):return self.value


class Pool:
    def __init__(self,**kwargs):self.futures=[]
    def submit(self,function,*args):
        result=Future(function,args);self.futures.append(result);return result
    def shutdown(self,**kwargs):pass


def prepared(source):
    h,w=source.shape[:2]
    return {'fields':{name:np.zeros((h,w,3) if name in ('intrusions','blemishes','banding') else (h,w),np.float32)
                      for name in ('intrusions','blemishes','uniformity','banding','enhancement')},
        'recovery':{name:np.zeros((h,w),np.float32) for name in S.RECOVERY},
        'masks':{name:np.zeros((h,w),np.float32) for name in ('background','floor','protect','intrusion','blemish')},
        'analysis':[],'method':'synthetic fixture only'}


def request(action='preview',*,pid='1'*32,mutation=None):
    result={'cmd':'studio_background_preview','action':action,'preview_id':pid,'session_id':'2'*32,'document_id':'load'}
    if action=='preview':result['mutation']=mutation or {'action':'view','target':'background'}
    return result


def apply_request(pid='3'*32):
    return {**request('apply',pid=pid),'cmd':'studio_background','request_id':'apply'}


def proposal():
    return {'parameters':{**S.parameters(),'enhancement':.4},'region_mode':'manual','strokes':[]}


def fixture(monkeypatch):
    engine=SimpleNamespace(_creative_base={'id':'synthetic'},_studio_background=S.empty(),
        _vram=SimpleNamespace(h=6,w=8,src_f32=Tensor(np.full((1,3,6,8),.4,np.float32))),
        _precompute=None,_precompute_backend='mediapipe',semantic=None,repair_key='repair-0')
    events=[];metadata={'document_id':'load','recipe_document_id':'recipe','recipe_revision':'0'}
    monkeypatch.setattr(D,'record',lambda e:e._creative_base)
    monkeypatch.setattr(D,'binding',lambda e:deepcopy(SOURCE))
    monkeypatch.setattr(P,'context',lambda e:(deepcopy(metadata),'projection'))
    monkeypatch.setattr(P,'ThreadPoolExecutor',Pool)
    monkeypatch.setattr(R,'verify',lambda e,v:C.validate(v,SOURCE))
    monkeypatch.setattr(C,'verify',lambda e,v:C.validate(v,SOURCE))
    def key(e,value):
        return (P._recipe_key(value),P._recipe_key(e._creative_base),e.repair_key,
                P._array_key(e._vram.src_f32.array),
                P._array_key(e.semantic) if value['region_mode']=='semantic_background' else None)
    monkeypatch.setattr(R,'key',key)
    monkeypatch.setattr(C,'preview',lambda e,value=None:(
        None if value is None or value['region_mode']=='manual' else {'mask':e.semantic.copy()},
        e._vram.src_f32.array[0].transpose(1,2,0),key(e,S.empty() if value is None else value)))
    monkeypatch.setattr(R,'semantic',lambda e,v:None if v['region_mode']=='manual' else e.semantic.copy())
    seen=[]
    def calculate(source,value,**kwargs):
        seen.append((source.copy(),deepcopy(value),kwargs.get('semantic_background')))
        return prepared(source)
    monkeypatch.setattr(P,'prepare',calculate)
    def stage(e,value,*,prepared):
        return SimpleNamespace(shape=(6,8),required=True,suspended=None,analysis=deepcopy(prepared['analysis']),
            fields={k:Tensor(v.copy()) for k,v in prepared['fields'].items()},
            recovery={k:Tensor(v.copy()) for k,v in prepared['recovery'].items()},verified_source_key=key(e,value))
    monkeypatch.setattr(R,'prepare_stage',stage)
    monkeypatch.setattr(P,'render',lambda *a:{'before':'before','after':'after'})
    owner=P.StudioPreview(engine,events.append);engine._studio_background_preview_owner=owner
    return engine,owner,events,seen


def complete(owner):
    owner.job['future'].complete();owner.tick()


def reviewed(monkeypatch):
    engine,owner,events,seen=fixture(monkeypatch)
    owner.handle(request());complete(owner);owner.handle(request('presented'))
    owner.handle(request(pid='3'*32,mutation={'action':'replace','target':'background','proposal':proposal()}))
    complete(owner);owner.handle(request('presented',pid='3'*32))
    assert events[-1]['state']=='presented'
    return engine,owner,events,seen


def test_proposal_uses_immutable_binding_not_original_file(monkeypatch):
    engine,_,_,_=fixture(monkeypatch)
    def original(_):raise AssertionError('must not bind original provenance pixels')
    monkeypatch.setattr(M,'bind_source',original)
    result=S.bind_proposal(engine,proposal())
    assert result['source']==SOURCE and result['semantic_owner'] is None
    engine._studio_background={**S.empty(),'source':{**SOURCE,'sha256':'b'*64}}
    with pytest.raises(ValueError):S.bind_proposal(engine,proposal())


def test_semantic_proposal_requires_actual_current_precompute(monkeypatch):
    engine,_,_,_=fixture(monkeypatch);candidate={**proposal(),'region_mode':'semantic_background'}
    with pytest.raises(ValueError):S.bind_proposal(engine,candidate)
    engine._precompute=SimpleNamespace(semantic_model_sha256='c'*64)
    seen=[];monkeypatch.setattr(D,'verify_precompute',lambda e,pc:seen.append(pc))
    value=S.bind_proposal(engine,candidate)
    assert seen==[engine._precompute] and value['semantic_owner']==M.current_owner(engine)
    def wrong(e,pc):raise ValueError('another composite inference input')
    monkeypatch.setattr(D,'verify_precompute',wrong)
    with pytest.raises(ValueError,match='another composite'):S.bind_proposal(engine,candidate)


def test_worker_measures_frozen_pre_repair_source_not_repair_base(monkeypatch):
    engine,owner,_,seen=fixture(monkeypatch)
    engine._vram.base=lambda:Tensor(np.full((1,3,6,8),.9,np.float32))
    owner.handle(request());frozen=owner.job['source']
    assert not frozen.flags.writeable and np.all(frozen==np.float32(.4))
    complete(owner)
    assert np.array_equal(seen[0][0],frozen) and owner.record is not None
    assert all(not a.flags.writeable for a in owner.record['prepared']['fields'].values())


@pytest.mark.parametrize('change',[
    lambda e:e._creative_base.update(id='other-immutable-source'),
    lambda e:setattr(e,'repair_key','repair-1'),
    lambda e:e._vram.src_f32.array.__setitem__((0,0,0,0),.6),
])
def test_async_completion_refuses_changed_source_without_document_revision(monkeypatch,change):
    engine,owner,events,_=fixture(monkeypatch)
    owner.handle(request());owner.job['future'].complete();change(engine);owner.tick()
    assert owner.record is None and events[-1]['state']=='failed'


def test_async_completion_refuses_changed_semantic_bytes_with_same_owner(monkeypatch):
    engine,owner,events,_=fixture(monkeypatch)
    engine.semantic=np.full((6,8),.8,np.float32)
    engine._studio_background={**S.empty(),'source':deepcopy(SOURCE),'region_mode':'semantic_background',
        'semantic_owner':{'backend':'mediapipe','contract':'same-model'}}
    owner.handle(request());owner.job['future'].complete();engine.semantic[0,0]=.2;owner.tick()
    assert owner.record is None and events[-1]['state']=='failed'


def test_latest_wins_discards_old_result_and_keeps_captured_proposal(monkeypatch):
    engine,owner,events,_=fixture(monkeypatch)
    owner.handle(request());old=owner.job
    owner.handle(request(pid='4'*32));assert old['stop'].is_set()
    old['future'].complete();owner.tick()
    assert owner.job['request']['preview_id']=='4'*32 and not events
    complete(owner)
    assert owner.record['request']['preview_id']=='4'*32
    assert [event['preview_id'] for event in events if event['state']=='ready']==['4'*32]


def test_changed_queued_source_fails_before_starting_next_worker(monkeypatch):
    engine,owner,events,_=fixture(monkeypatch)
    owner.handle(request());old=owner.job;owner.handle(request(pid='4'*32))
    old['future'].complete();engine._vram.src_f32.array[0,0,0,0]=.2;owner.tick()
    assert owner.job is None and owner.latest is None and events[-1]['state']=='failed'
    assert len(owner.pool.futures)==1


def test_presented_and_apply_recheck_prepared_bytes_and_gpu_versions(monkeypatch):
    _,owner,_,_=reviewed(monkeypatch)
    value,stage=owner.prepare(apply_request())
    assert value['source']==SOURCE and stage is owner.record['stage']
    stage.fields['enhancement']._version+=1
    with pytest.raises(ValueError):owner.prepare(apply_request())
    stage.fields['enhancement']._version-=1
    mask=owner.record['prepared']['masks']['background'];mask.setflags(write=True);mask[0,0]=1.
    with pytest.raises(ValueError):owner.verify_record(request('presented',pid='3'*32))


def test_apply_refuses_proposal_tampering_or_unpresented_or_view_only(monkeypatch):
    _,owner,_,_=reviewed(monkeypatch)
    owner.record['presented']=False
    with pytest.raises(ValueError):owner.prepare(apply_request())
    owner.record['presented']=True;owner.record['committable']=False
    with pytest.raises(ValueError):owner.prepare(apply_request())
    owner.record['committable']=True;owner.record['value']['parameters']['enhancement']=.7
    with pytest.raises(ValueError):owner.prepare(apply_request())


def test_cancelled_future_cannot_republish_old_review(monkeypatch):
    _,owner,events,_=fixture(monkeypatch)
    owner.handle(request());old=owner.job;owner.handle(request('cancel'))
    old['future'].complete();owner.tick()
    assert owner.session is None and owner.record is None
    assert [event['state'] for event in events]==['cancelled']


def test_exact_host_admission_does_not_open_other_background_tools(monkeypatch):
    engine,owner,_,_=reviewed(monkeypatch)
    H.require_command(engine,'studio_background',apply_request())
    H.require_command(engine,'studio_background_preview',request('presented',pid='3'*32))
    H.require_command(engine,'studio_background_preview',request('cancel',pid='3'*32))
    assert owner.record is not None  # Guard does not consume the native receipt.
    for name in ('background','sky_replacement','optics'):
        with pytest.raises(ValueError):H.require_command(engine,name,{**apply_request(),'cmd':name})
    for wrong in ({**apply_request(),'action':'state'},{**apply_request(),'source':SOURCE},
                  {**request(),'mutation':{'action':'view','target':'guessed_floor'}}):
        with pytest.raises(ValueError):H.require_command(engine,wrong['cmd'],wrong)


def test_host_requires_actual_pipeline_for_view_but_stale_cancel_can_release(monkeypatch):
    engine,_,_,_=fixture(monkeypatch)
    def wrong(*args):raise ValueError('foreign actual pipeline pixels')
    monkeypatch.setattr(C,'preview',wrong)
    command=request()
    with pytest.raises(ValueError,match='foreign actual'):H.require_command(engine,command['cmd'],command)
    H.require_command(engine,'studio_background_preview',request('cancel'))


def test_exact_native_terminal_receipt_survives_consumed_review(monkeypatch):
    engine,_,_,_=fixture(monkeypatch);command=apply_request()
    digest=sha256(json.dumps(command,sort_keys=True,allow_nan=False).encode()).hexdigest()
    receipt={'success':True,'history':{'undo_steps':1,'redo_steps':0}}
    engine._studio_background_owner=SimpleNamespace(cache={'apply':(digest,receipt)})
    engine._studio_background_preview_owner=None;engine._creative_base=None
    H.require_command(engine,'studio_background',command)
    assert engine._studio_background_owner.cache['apply'][1] is receipt
    with pytest.raises(ValueError,match='different content'):
        H.require_command(engine,'studio_background',{**command,'preview_id':'5'*32})
