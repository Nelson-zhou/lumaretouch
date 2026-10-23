"""AUTHORED / UNRUN: canonical sky transport through preview and strict export.

Synthetic semantic fields, canonical owners, stages and prepare callbacks isolate
the transport/proof boundary. These are not model, native raster, GPU, visual,
export-quality or product acceptance results.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import sky_replacement_runtime as R,sky_replacement_state as S
from lumaretouch_engine import creative_derived_sky as C,cpu_memory_budget as MB
from lumaretouch_engine.sky_semantic import immutable_input as I,manifest as M,resolver as SR,state as SS

SOURCE={'sha256':'a'*64,'width':8,'height':6}
ASSET={'path':'/chosen-sky.png','sha256':'b'*64,'width':8,'height':6,
       'bits':8,'working_color':'encoded-srgb','icc_sha256':None}
SOURCE_STAMP=(1,2,3,4,5)
ASSET_STAMP=(6,7,8,9,10)


def pixels():
    return np.full((6,8,3),.4,np.float32)


def recipe(*,enabled=True):
    packet=I.from_pixels(pixels(),SOURCE)
    descriptor=SS.check({'version':1,'domain':'source-normalized','source':deepcopy(SOURCE),
        'model':M.identity(),'host':{key:'fixture' for key in ('python','torch','torchvision','numpy','Pillow')},
        'device':'cpu','input_sha256':packet['input_sha256'],'input_size':packet['input_size'],
        'fields_sha256':{key:'c'*64 for key in SS.REGIONS},'regions':{'sky':.5}})
    value=S.empty();value.update(enabled=enabled,source=deepcopy(SOURCE),asset=deepcopy(ASSET),
                                 person_mode='none',semantic=descriptor)
    return S.check(value),packet


def raster_fixture(monkeypatch):
    seen=[]
    monkeypatch.setattr(MB,'available_estimate',lambda:8*1024**3)
    monkeypatch.setattr(R.B.R,'raster',lambda stack,shape:np.zeros(shape,np.uint8))
    def resolve(descriptor,path,**kwargs):
        seen.append((deepcopy(descriptor),path,kwargs))
        return {'owned':'synthetic semantic fields'}
    def region(stack,shape,descriptor,fields,target):
        assert fields=={'owned':'synthetic semantic fields'}
        field=np.zeros(shape,np.uint8)
        if target=='sky':field[:2]=255
        return field
    monkeypatch.setattr(SR,'resolve',resolve);monkeypatch.setattr(SR,'raster_region',region)
    return seen


def test_raster_passes_exact_packet_with_no_original_path(monkeypatch):
    seen=raster_fixture(monkeypatch);value,packet=recipe()
    result=R.raster(value,(6,8),immutable_input=packet,force_semantic=True)
    assert seen[0][1] is None and I.key(seen[0][2]['immutable_input'])==I.key(packet)
    assert seen[0][2]['force'] is True and np.any(result['sky']) and not np.all(result['sky'])


def test_original_raster_retains_file_route_without_packet(monkeypatch):
    seen=raster_fixture(monkeypatch);value,_=recipe()
    R.raster(value,(6,8),source_path='/physical-original.jpg')
    assert seen[0][1]=='/physical-original.jpg' and seen[0][2]['immutable_input'] is None


def test_raster_rejects_dual_source_and_explicit_capture_error_before_resolve(monkeypatch):
    seen=raster_fixture(monkeypatch);value,packet=recipe()
    with pytest.raises(ValueError):
        R.raster(value,(6,8),source_path='/physical-original.jpg',immutable_input=packet)
    with pytest.raises(ValueError,match='canonical unavailable'):
        R.raster(value,(6,8),immutable_error='canonical unavailable')
    assert seen==[]


def test_disabled_raster_failure_preserves_semantic_intent_and_manual_locator(monkeypatch):
    seen=raster_fixture(monkeypatch);value,packet=recipe(enabled=False)
    def failed(descriptor,path,**kwargs):
        seen.append((descriptor,path,kwargs));raise ValueError('pinned model missing')
    monkeypatch.setattr(SR,'resolve',failed)
    prepared=R.prepare(value,(6,8),immutable_input=packet)
    assert prepared['value']['semantic']==value['semantic'] and prepared['semantic_suspended']=='pinned model missing'
    assert prepared['fields'] is None and all(not np.any(field) for field in prepared['raw_fields'].values())
    assert len(seen)==1 and seen[0][1] is None


def export_fixture(monkeypatch):
    value,packet=recipe();source=pixels();calls=[];installation=['installed']
    spec=SimpleNamespace(creative_base={'id':'derived'},sky_replacement=value,
        sky_replacement_path='/physical-original.jpg',sky_replacement_stamp=list(SOURCE_STAMP))
    monkeypatch.setattr(R.B,'file_stamp',lambda path:ASSET_STAMP if path==ASSET['path'] else SOURCE_STAMP)
    monkeypatch.setattr(M,'installation_stamp',lambda:tuple(installation))
    expected=source.copy()
    def verify(owner,actual):
        calls.append('verify')
        assert owner is spec
        if not np.array_equal(actual,expected):raise ValueError('canonical pixels changed')
    monkeypatch.setattr(C,'verify_export',verify)
    build=I.from_pixels
    def from_pixels(actual,binding):
        calls.append('packet')
        assert calls[-2]=='verify' and actual is source and binding==SOURCE
        return build(actual,binding)
    monkeypatch.setattr(I,'from_pixels',from_pixels)
    def prepare(actual,shape,**kwargs):
        calls.append('prepare')
        assert actual==value and shape==(6,8) and kwargs['source_path'] is None
        assert kwargs['force_semantic'] is True and I.key(kwargs['immutable_input'])==I.key(packet)
        return {'value':deepcopy(actual),'asset_stamp':ASSET_STAMP}
    monkeypatch.setattr(R,'prepare',prepare)
    return spec,source,calls,installation,prepare


def test_export_packet_is_built_after_canonical_verification_and_strictly_replayed(monkeypatch):
    spec,source,calls,_,_=export_fixture(monkeypatch)
    R.export_prepare(spec,(6,8),source_pixels=source)
    assert calls==['verify','packet','prepare','verify']
    assert spec.sky_replacement_prepared['value']==spec.sky_replacement
    assert spec._sky_replacement_immutable_input['source']==SOURCE
    R.finish_export(spec)


def test_export_never_builds_packet_from_unverified_source(monkeypatch):
    spec,source,calls,_,_=export_fixture(monkeypatch);source[0,0,0]=.7
    with pytest.raises(ValueError,match='canonical'):
        R.export_prepare(spec,(6,8),source_pixels=source)
    assert calls==['verify'] and spec.sky_replacement_prepared is None


@pytest.mark.parametrize('mutate',[
    lambda spec,source,installation:source.__setitem__((0,0,0),.7),
    lambda spec,source,installation:spec.sky_replacement['semantic']['regions'].__setitem__('sky',.9),
    lambda spec,source,installation:installation.__setitem__(0,'replaced'),
])
def test_export_rechecks_source_proposal_and_installation_after_prepare(monkeypatch,mutate):
    spec,source,_,installation,prepare=export_fixture(monkeypatch)
    def changing(*args,**kwargs):
        prepared=prepare(*args,**kwargs);mutate(spec,source,installation);return prepared
    monkeypatch.setattr(R,'prepare',changing)
    with pytest.raises(ValueError):R.export_prepare(spec,(6,8),source_pixels=source)
    assert spec.sky_replacement_prepared is None and spec._sky_replacement_replay_key is None


@pytest.mark.parametrize('mutate',[
    lambda spec,installation:spec._sky_replacement_immutable_input.__setitem__('pixels',b'changed'),
    lambda spec,installation:spec.sky_replacement['semantic']['regions'].__setitem__('sky',.9),
    lambda spec,installation:spec.sky_replacement.__setitem__('enabled',False),
    lambda spec,installation:installation.__setitem__(0,'removed'),
])
def test_export_completion_rejects_changed_packet_proposal_or_model(monkeypatch,mutate):
    spec,source,_,installation,_=export_fixture(monkeypatch)
    R.export_prepare(spec,(6,8),source_pixels=source);mutate(spec,installation)
    with pytest.raises(ValueError):R.finish_export(spec)


def test_original_export_keeps_verified_file_replay(monkeypatch):
    value,_=recipe();seen=[]
    spec=SimpleNamespace(creative_base=None,sky_replacement=value,sky_replacement_path='/original.jpg',
                         sky_replacement_stamp=list(SOURCE_STAMP))
    monkeypatch.setattr(R.B,'file_stamp',lambda path:SOURCE_STAMP)
    monkeypatch.setattr(R.B,'verify_source',lambda *args:seen.append(('verify',args)))
    def forbidden(*args,**kwargs):raise AssertionError('Original export must not construct a derived input')
    monkeypatch.setattr(I,'from_pixels',forbidden);monkeypatch.setattr(C,'verify_export',forbidden)
    def prepare(value,shape,**kwargs):seen.append(('prepare',kwargs));return {'asset_stamp':SOURCE_STAMP}
    monkeypatch.setattr(R,'prepare',prepare)
    R.export_prepare(spec,(6,8))
    assert [item[0] for item in seen]==['verify','prepare']
    assert seen[1][1]['source_path']=='/original.jpg' and seen[1][1]['immutable_input'] is None
    assert seen[1][1]['force_semantic'] is True


class Stage:
    def __init__(self,device,shape):self.suspended=None;self.value=S.empty()
    def set(self,value,prepared=None,*,reason=None):self.value=deepcopy(value);self.suspended=reason


def cached_engine(monkeypatch):
    value,packet=recipe();installation=['installed']
    stage=Stage('cpu',(6,8));stage.value=value
    pipe=SimpleNamespace(h=6,w=8,device='cpu',sky_replacement=stage)
    engine=SimpleNamespace(_creative_base={'id':'derived'},_sky_replacement=value,_vram=pipe,
                           _docs=[{'path':'/physical-original.jpg'}],_doc_index=0)
    monkeypatch.setattr(C,'key',lambda engine,value:('synthetic-live-proof',))
    monkeypatch.setattr(C,'semantic_input',lambda engine:deepcopy(packet))
    monkeypatch.setattr(M,'installation_stamp',lambda:tuple(installation))
    monkeypatch.setattr(R,'SkyReplacementStage',Stage)
    def forbidden(*args,**kwargs):raise AssertionError('Derived stage must not open physical original as model input')
    monkeypatch.setattr(R.B,'file_stamp',forbidden)
    pipe._sky_replacement_key=R.stage_key(engine,value)
    return engine,packet,installation


def test_derived_stage_key_tracks_installation_identity(monkeypatch):
    engine,_,installation=cached_engine(monkeypatch);before=R.stage_key(engine,engine._sky_replacement)
    installation[0]='removed'
    assert R.stage_key(engine,engine._sky_replacement)!=before


def test_strict_cache_hit_replays_only_canonical_packet(monkeypatch):
    engine,packet,_=cached_engine(monkeypatch);seen=[]
    def resolve(descriptor,path,**kwargs):seen.append((path,kwargs))
    monkeypatch.setattr(SR,'resolve',resolve)
    R.sync(engine,strict=True)
    assert len(seen)==1 and seen[0][0] is None and seen[0][1]['force'] is True
    assert I.key(seen[0][1]['immutable_input'])==I.key(packet)


def test_nonstrict_cache_hit_still_checks_packet_against_reviewed_proposal(monkeypatch):
    engine,_,_=cached_engine(monkeypatch)
    engine._sky_replacement['semantic']['input_sha256']='f'*64
    R.sync(engine)
    assert engine._vram.sky_replacement.suspended
