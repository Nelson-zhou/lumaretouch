"""AUTHORED / UNRUN: returned-source sky LIVE ownership and review contracts.

Synthetic tensors, jobs, rasters and rendering do not establish product, native
mask, model, visual quality, GPU, export or history transaction acceptance.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import numpy as np
import pytest
from lumaretouch_engine import sky_replacement_state as S,sky_replacement_preview as P
from lumaretouch_engine import sky_replacement_runtime as R,sky_replacement_assets as A
from lumaretouch_engine import creative_sky_host as H,creative_derived_source as D,creative_derived_sky as C
from lumaretouch_engine import local_mask_state as M

SOURCE={'sha256':'a'*64,'width':8,'height':6}
ASSET={'path':'/chosen-sky.png','sha256':'b'*64,'width':8,'height':6,
       'bits':8,'working_color':'encoded-srgb','icc_sha256':None}
STAMP=(1,2,3,4,5)


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
    def complete(self):
        try:self.value=self.function(*self.args);self.error=None
        except Exception as error:self.error=error
        self.finished=True
    def done(self):return self.finished
    def result(self):
        if self.error is not None:raise self.error
        return self.value


class Pool:
    def __init__(self,**kwargs):self.futures=[]
    def submit(self,function,*args):
        result=Future(function,args);self.futures.append(result);return result
    def shutdown(self,**kwargs):pass


class Stage:
    def __init__(self,device,shape):
        self.device=device;self.shape=shape;self.set(S.empty())
    def set(self,value,prepared=None):
        self.value=deepcopy(value);self.fields={};self.suspended=None;self.asset_stamp=None
        self.sky=self.reflection=self.tint=self.horizon_weight=self.sky_valid=self.reflection_valid=None
        if value['enabled']:
            self.asset_stamp=prepared['asset_stamp']
            self.fields={name:Tensor(field.copy()) for name,field in prepared['fields'].items()}
            self.sky=Tensor(prepared['asset'].copy());self.reflection=Tensor(prepared['reflection'].copy())
            self.tint=Tensor(prepared['tint'].copy());self.horizon_weight=Tensor(np.ones(self.shape,np.float32))
            self.sky_valid=Tensor(np.ones(self.shape,np.float32));self.reflection_valid=Tensor(np.ones(self.shape,np.float32))


def request(action='preview',*,pid='1'*32,mutation=None):
    result={'cmd':'sky_replacement_preview','action':action,'preview_id':pid,'session_id':'2'*32,'document_id':'load'}
    if action=='preview':result['mutation']=mutation or {'action':'view','target':'sky'}
    return result


def apply_request(pid='3'*32):
    return {**request('apply',pid=pid),'cmd':'sky_replacement','request_id':'apply'}


def brush(name):
    return {'id':name,'name':name,'enabled':True,'kind':'brush','operation':'add','opacity':1.,'feather':0.,
            'axes':[[.1,0.],[0.,.1]],'points':[[.5,.2]]}


def draft(*,enabled=True,choice='4'*32):
    raw=S.editable(S.empty());raw.update(enabled=enabled,asset_path=ASSET['path'],asset_choice=choice,person_mode='none')
    raw['regions']['sky']['objects']=[brush('manual-sky')]
    return raw


def fixture(monkeypatch):
    pipe=SimpleNamespace(h=6,w=8,device='cpu',src_f32=Tensor(np.full((1,3,6,8),.4,np.float32)),
                         has_background=lambda:False)
    engine=SimpleNamespace(_creative_base={'id':'returned-source'},_sky_replacement=S.empty(),_vram=pipe,
        _doc_index=0,_docs=[{'path':'/physical-original.jpg'}],repair_key='repair-0',warp_key='warp-0',projection='projection-0')
    events=[];metadata={'document_id':'load','recipe_document_id':'recipe','recipe_revision':'0'}
    assets={ASSET['path']:A.SkyAsset(deepcopy(ASSET),np.full((6,8,3),128,np.uint8),STAMP)};reads=[];calculations=[]
    monkeypatch.setattr(D,'record',lambda e:e._creative_base)
    monkeypatch.setattr(D,'binding',lambda e:deepcopy(SOURCE))
    monkeypatch.setattr(P,'context',lambda e:(deepcopy(metadata),e.projection))
    monkeypatch.setattr(P,'ThreadPoolExecutor',Pool);monkeypatch.setattr(P,'SkyReplacementStage',Stage)
    monkeypatch.setattr(P,'image',lambda tensor,projection:('source', (8,6)))
    monkeypatch.setattr(P,'render',lambda *args:{'after':'production-output'})
    def stamp(path):
        if path not in assets:raise ValueError('linked asset missing')
        return assets[path].stamp
    monkeypatch.setattr(M,'file_stamp',stamp)
    def read(path,*,expected=None,cancelled=lambda:False):
        reads.append((path,deepcopy(expected)))
        if path not in assets:raise ValueError('linked asset missing')
        asset=assets[path]
        if expected is not None and expected!=asset.binding:raise ValueError('linked asset identity changed')
        return asset
    monkeypatch.setattr(A,'read',read)
    monkeypatch.setattr(A,'verify',lambda value:read(value['path'],expected=value).stamp)
    def key(e,value):
        return (P._recipe_key(value),P._recipe_key(e._creative_base),e.repair_key,e.warp_key,
                P._array_key(e._vram.src_f32.array),stamp(value['asset']['path']) if value['enabled'] else None)
    def verify(e,value):
        value=C.validate(value,SOURCE)
        if value['enabled']:A.verify(value['asset'])
        return value
    monkeypatch.setattr(R,'verified_value',verify);monkeypatch.setattr(C,'verify',verify)
    monkeypatch.setattr(R,'stage_key',key);monkeypatch.setattr(C,'key',key)
    monkeypatch.setattr(C,'preview',lambda e,value=None:(None,e._vram.src_f32.array[0].transpose(1,2,0),
                                                       key(e,S.empty() if value is None else value)))
    def prepare(value,shape,*,asset=None,**kwargs):
        calculations.append(deepcopy(value));S.ready(value)
        assert value['semantic'] is None  # No physical-original semantic resolver.
        raw={name:np.zeros(shape,np.uint8) for name in (*S.REGIONS,'recovery')};raw['sky'][:2]=255
        result={'value':deepcopy(value),'shape':shape,'raw_fields':raw,'fields':None,'semantic_suspended':None}
        if value['enabled']:
            result.update(fields={name:field.astype(np.float32)/255. for name,field in raw.items()},
                asset=np.full((6,8,3),.4,np.float32),reflection=np.full((6,8,3),.4,np.float32),
                tint=np.ones(3,np.float32),cover=1.,asset_stamp=asset.stamp)
        return result
    monkeypatch.setattr(R,'prepare',prepare)
    owner=P.SkyPreview(engine,events.append);engine._sky_replacement_preview_owner=owner
    return engine,owner,events,assets,reads,calculations


def complete(owner):
    owner.job['future'].complete();owner.tick()


def shown(monkeypatch):
    state=fixture(monkeypatch);_,owner,events,*_=state
    owner.handle(request());complete(owner);owner.handle(request('presented'))
    assert events[-1]['state']=='presented'
    return state


def reviewed(monkeypatch):
    state=shown(monkeypatch);_,owner,events,*_=state
    owner.handle(request(pid='3'*32,mutation={'action':'replace','target':'sky','draft':draft()}))
    complete(owner);owner.handle(request('presented',pid='3'*32))
    assert events[-1]['state']=='presented'
    return state


def test_locator_and_manual_vectors_bind_returned_source_not_original(monkeypatch):
    engine,owner,_,_,_,_=fixture(monkeypatch)
    def original(*args):raise AssertionError('physical-original binding must not be used')
    monkeypatch.setattr(M,'bind_source',original)
    owner.handle(request());complete(owner);owner.handle(request('presented'))
    assert owner.session['binding']==SOURCE
    raw=draft();raw['person_mode']='marked';raw['regions']['person']['objects']=[brush('manual-person')]
    raw['regions']['water']['objects']=[brush('manual-water')];raw['recovery']['objects']=[brush('manual-recovery')]
    owner.handle(request(pid='3'*32,mutation={'action':'replace','target':'recovery','draft':raw}))
    complete(owner);owner.handle(request('presented',pid='3'*32))
    value,_=owner.prepare(apply_request())
    assert value['source']==SOURCE and value['recovery']['objects'][0]['id']=='manual-recovery'
    assert all(value['regions'][target]['objects'] for target in S.REGIONS)


@pytest.mark.parametrize('change',[
    lambda e:e._creative_base.update(id='another-source'),
    lambda e:setattr(e,'repair_key','repair-1'),
    lambda e:setattr(e,'warp_key','warp-1'),
    lambda e:setattr(e,'projection','projection-1'),
    lambda e:e._vram.src_f32.array.__setitem__((0,0,0,0),.6),
])
def test_async_ready_rejects_changed_actual_source_without_revision(monkeypatch,change):
    engine,owner,events,*_=fixture(monkeypatch)
    owner.handle(request());owner.job['future'].complete();change(engine);owner.tick()
    assert owner.record is None and events[-1]['state']=='failed'


def test_latest_wins_discards_old_result_and_does_not_rebind_queued_input(monkeypatch):
    engine,owner,events,*_=fixture(monkeypatch)
    owner.handle(request());old=owner.job;owner.handle(request(pid='5'*32))
    assert old['stop'].is_set()
    old['future'].complete();engine.repair_key='repair-1';owner.tick()
    assert owner.job is None and owner.latest is None and events[-1]['state']=='failed'
    assert len(owner.pool.futures)==1


def test_job_owns_frozen_recipe_and_explicit_asset_selection(monkeypatch):
    _,owner,events,*_=shown(monkeypatch);raw=draft()
    owner.handle(request(pid='3'*32,mutation={'action':'replace','target':'sky','draft':raw}))
    raw['parameters']['opacity']=12.
    assert owner.job['raw']['parameters']['opacity']==100.
    owner.job['raw']['parameters']['opacity']=23.;complete(owner)
    assert owner.record is None and events[-1]['state']=='failed'


@pytest.mark.parametrize('group,name', [('raw_fields','sky'),('fields','recovery'),(None,'asset'),(None,'tint')])
def test_presented_and_apply_recheck_prepared_bytes(monkeypatch,group,name):
    _,owner,_,*_=reviewed(monkeypatch)
    value,stage=owner.prepare(apply_request());assert value['source']==SOURCE and stage is owner.record['stage']
    prepared=owner.record['prepared'];field=prepared[group][name] if group else prepared[name]
    assert not field.flags.writeable
    field.setflags(write=True);field.flat[0]=.2 if field.dtype==np.float32 else 12
    with pytest.raises(ValueError):owner.verify_record(request('presented',pid='3'*32))
    with pytest.raises(ValueError):owner.prepare(apply_request())


@pytest.mark.parametrize('name',['sky','reflection','tint','horizon_weight','sky_valid','reflection_valid'])
def test_apply_rechecks_stage_tensor_identity_and_version(monkeypatch,name):
    _,owner,_,*_=reviewed(monkeypatch)
    getattr(owner.record['stage'],name)._version+=1
    with pytest.raises(ValueError):owner.prepare(apply_request())


def test_stage_region_tensor_and_resolved_asset_mutation_are_rejected(monkeypatch):
    _,owner,_,*_=reviewed(monkeypatch)
    owner.record['stage'].fields['water']._version+=1
    with pytest.raises(ValueError):owner.prepare(apply_request())
    owner.record['stage'].fields['water']._version-=1
    owner.record['resolved_asset'].pixels[0,0,0]=11
    with pytest.raises(ValueError):owner.prepare(apply_request())


def test_asset_changed_after_ready_cannot_be_presented_or_applied(monkeypatch):
    _,owner,_,assets,*_=reviewed(monkeypatch)
    old=assets[ASSET['path']];assets[ASSET['path']]=A.SkyAsset(old.binding,old.pixels,STAMP[:-1]+(9,))
    with pytest.raises(ValueError):owner.verify_record(request('presented',pid='3'*32))
    with pytest.raises(ValueError):owner.prepare(apply_request())


def test_display_render_mutation_cannot_publish_ready(monkeypatch):
    _,owner,events,*_=shown(monkeypatch)
    def render(engine,stage,*args):stage.sky._version+=1;return {'after':'changed-stage'}
    monkeypatch.setattr(P,'render',render)
    owner.handle(request(pid='3'*32,mutation={'action':'replace','target':'sky','draft':draft()}));complete(owner)
    assert owner.record is None and events[-1]['state']=='failed'


def test_missing_link_retains_locator_then_explicit_disable_keeps_identity(monkeypatch):
    engine,owner,events,assets,reads,_=fixture(monkeypatch)
    engine._sky_replacement=S.from_editable(draft(choice=None),SOURCE,ASSET);assets.clear()
    H.require_command(engine,'sky_replacement_preview',request())
    owner.handle(request());complete(owner)
    assert events[-1]['state']=='ready' and not events[-1]['committable'] and events[-1]['validation_error']
    owner.handle(request('presented'));reads.clear()
    raw=S.editable(engine._sky_replacement);raw['enabled']=False
    owner.handle(request(pid='3'*32,mutation={'action':'replace','target':'sky','draft':raw}));complete(owner)
    owner.handle(request('presented',pid='3'*32));value,_=owner.prepare(apply_request())
    assert not value['enabled'] and value['asset']==ASSET and value['source']==SOURCE and not reads


def test_same_choice_cannot_silently_select_another_link(monkeypatch):
    _,owner,events,*_=reviewed(monkeypatch)
    raw=draft();raw['asset_path']='/another-sky.png'
    owner.handle(request(pid='5'*32,mutation={'action':'replace','target':'sky','draft':raw}));complete(owner)
    assert events[-1]['state']=='ready' and events[-1]['validation_error'] and not events[-1]['committable']
    assert owner.session['asset_choices']['4'*32]==ASSET


def test_new_path_without_explicit_choice_is_not_committable(monkeypatch):
    _,owner,events,*_=shown(monkeypatch)
    owner.handle(request(pid='3'*32,mutation={'action':'replace','target':'sky','draft':draft(choice=None)}));complete(owner)
    assert not events[-1]['committable'] and events[-1]['validation_error']


def test_semantic_draft_never_starts_worker_or_fallback_resolver(monkeypatch):
    engine,owner,events,_,_,calculations=shown(monkeypatch);count=len(calculations)
    raw=draft();raw['semantic']={'unsupported':'must not reach original-photo resolver'}
    command=request(pid='3'*32,mutation={'action':'replace','target':'sky','draft':raw})
    with pytest.raises(ValueError):H.require_command(engine,command['cmd'],command)
    owner.handle(command)
    assert owner.job is None and events[-1]['state']=='failed' and len(calculations)==count


def test_worker_transport_independently_rejects_semantic_before_work(monkeypatch):
    _,owner,_,_,_,calculations=shown(monkeypatch);count=len(calculations)
    owner.handle(request(pid='3'*32,mutation={'action':'replace','target':'sky','draft':draft()}))
    job=owner.job;job['raw']['semantic']={'stale':'unsupported proposal'}
    job['input_key']=P._job_key(job)  # Simulate a caller that bypassed UI admission.
    with pytest.raises(ValueError):
        P._work_owned(job,(6,8),SimpleNamespace(is_set=lambda:False))
    assert len(calculations)==count


def test_view_only_unpresented_and_changed_recipe_cannot_commit(monkeypatch):
    _,owner,_,*_=shown(monkeypatch)
    with pytest.raises(ValueError):owner.prepare(apply_request(pid='1'*32))
    owner.handle(request(pid='3'*32,mutation={'action':'replace','target':'sky','draft':draft()}));complete(owner)
    with pytest.raises(ValueError):owner.prepare(apply_request())
    owner.handle(request('presented',pid='3'*32));owner.record['value']['parameters']['opacity']=40.
    with pytest.raises(ValueError):owner.prepare(apply_request())


def test_cancel_releases_stale_review_before_actual_source_checks(monkeypatch):
    engine,owner,events,*_=fixture(monkeypatch)
    owner.handle(request());old=owner.job
    monkeypatch.setattr(C,'preview',lambda *args:(_ for _ in ()).throw(ValueError('stale actual source')))
    H.require_command(engine,'sky_replacement_preview',request('cancel'));owner.handle(request('cancel'))
    old['future'].complete();owner.tick()
    assert owner.session is None and owner.record is None
    assert [event['state'] for event in events]==['cancelled']


def test_exact_host_only_admits_native_manual_review_route(monkeypatch):
    engine,owner,_,*_=reviewed(monkeypatch)
    H.require_command(engine,'sky_replacement',apply_request())
    H.require_command(engine,'sky_replacement_preview',request('presented',pid='3'*32))
    assert owner.record is not None  # Admission never consumes native history/receipt ownership.
    for name in ('sky_semantic','background','sky_replacement_preset','studio_background'):
        with pytest.raises(ValueError):H.require_command(engine,name,{**apply_request(),'cmd':name})
    for bad in ({**apply_request(),'action':'state'},{**apply_request(),'source':SOURCE},
                {**request(),'mutation':{'action':'view','target':'guessed-sky'}}):
        with pytest.raises(ValueError):H.require_command(engine,bad['cmd'],bad)


def test_terminal_native_receipt_replays_without_live_source_or_review(monkeypatch):
    engine,_,_,*_=fixture(monkeypatch);command=apply_request()
    digest=sha256(json.dumps(command,sort_keys=True,allow_nan=False).encode()).hexdigest()
    receipt={'success':True,'history':{'undo_steps':1,'redo_steps':0}}
    engine._sky_replacement_owner=SimpleNamespace(cache={'apply':(digest,receipt)})
    engine._creative_base=None;engine._sky_replacement_preview_owner=None
    H.require_command(engine,'sky_replacement',command)
    assert engine._sky_replacement_owner.cache['apply'][1] is receipt
    with pytest.raises(ValueError,match='different content'):
        H.require_command(engine,'sky_replacement',{**command,'preview_id':'6'*32})
