"""Levels survive state, project, scope, batch, export and the actual inspection worker."""
import copy
from pathlib import Path
import numpy as np
import pytest
from lumaretouch_engine.ops import levels as L
from test_protocol import engine


def recipe():
    value=L.default_levels();value['master']['gamma']=2.
    return value


def test_state_restore_validates_before_mutation_and_old_projects_are_neutral():
    from lumaretouch_engine.server import Engine
    e=Engine('levels-state');original=e._capture_state();bad=copy.deepcopy(original)
    bad['_strength']=.7;bad['_levels']['master']['input_white']=0
    with pytest.raises(ValueError):e._apply_state(bad)
    assert e._strength==original['_strength'] and L.is_identity(e._levels)
    e._levels=recipe();old=e._fresh_doc_state();old.pop('_levels');e._apply_state(old)
    assert L.is_identity(e._levels)


def test_levels_history_gesture_and_snapshot_export_contract():
    from lumaretouch_engine.server import Engine
    from lumaretouch_engine.export_recipe import build_export_spec
    e=Engine('levels-history');before=e._history_capture();e._levels=recipe()
    group=e._history_group('levels',{'gesture_id':'drag'})
    assert group=='levels:gesture:drag'
    e._history_record(group,before);assert len(e._undo)==1
    snapshot=e._state_to_export_snap(e._capture_state(),device='cpu',scale=1,upscale_backend='lanczos3',sharpen=0)
    spec,skipped=build_export_spec(snapshot,64,96,for_document=True)
    assert spec.levels==recipe() and skipped==[]
    assert '色阶（有有效调整）' in e._master16_blockers(scale=1,sharpen=0)
    changed=e._history_capture();e._levels=L.default_levels();e._history_record(group,changed)
    assert len(e._undo)==0


def test_project_file_and_module_preset_round_trip(tmp_path):
    from PIL import Image
    from lumaretouch_engine import project as P,scope as S,manual_liquify_state as ML
    path=tmp_path/'source.png';Image.fromarray(np.full((32,24,3),100,np.uint8)).save(path)
    original=path.read_bytes();project=P.new_project('levels',str(tmp_path))
    P.add_doc(project,str(path),{'_manual_liquify':ML.empty(),'_levels':recipe()});saved=P.project_path_for(str(tmp_path),'levels')
    P.save(project,saved);restored,dropped=P.active_recipe(P.load(saved),str(path))
    assert dropped==[] and restored['_levels']==recipe() and path.read_bytes()==original
    preset=S.validate_preset({'schema':S.PRESET_SCHEMA,'id':'levels-test','name':'Levels','kind':'custom',
        'modules':{S.OP_LEVELS:{'recipe':recipe()}}})
    applied=S.apply_modules({'untouched':True},preset['modules'])
    assert applied['_levels']==recipe() and applied['untouched'] is True


def test_batch_levels_scope_and_undo_are_independent():
    from test_batch_sync_controller import fixture
    from lumaretouch_engine.scope import OP_LEVELS
    c,rows,_,events,_,_=fixture();rows[0]['state']['_levels']=recipe()
    c.handle_command({'action':'commit','docs':[1],'module_scope':[OP_LEVELS]})
    assert rows[1]['state']['_levels']==recipe() and rows[1]['state']['_exposure'][0]==0
    c.handle_command({'action':'undo','batch_id':c.summary()['last']})
    assert L.is_identity(rows[1]['state'].get('_levels'))


def test_rgb8_rgb16_export_share_levels_without_eight_bit_quantization():
    pytest.importorskip('torch')
    from lumaretouch_engine.export import ExportSpec,export_image,export_image16
    source=np.broadcast_to(np.linspace(0,65535,513,dtype=np.uint16)[None,:,None],(64,513,3)).copy()
    value=recipe();value['red']['input_black']=.05
    expected=np.rint(np.clip(L.levels_np(source.astype(np.float32)/65535,value),0,1)*65535).astype(np.uint16)
    actual,_=export_image16(source,ExportSpec(strength=0,levels=value),device='cpu',tile=256)
    assert np.max(np.abs(actual.astype(np.int32)-expected.astype(np.int32)))<=2
    assert len(np.unique(actual[0,:,1]))>256
    source8=np.rint(source.astype(np.float32)/257).astype(np.uint8)
    expected8=np.rint(np.clip(L.levels_np(source8.astype(np.float32)/255,value),0,1)*255).astype(np.uint8)
    actual8,_=export_image(source8,ExportSpec(strength=0,levels=value),device='cpu',tile=256)
    assert np.max(np.abs(actual8.astype(np.int32)-expected8.astype(np.int32)))<=1


def test_actual_protocol_inspection_undo_and_stale_document_fence(engine,tmp_path):
    pytest.importorskip('torch')
    from PIL import Image
    from test_inspection_runtime import config
    data=np.full((64,96,3),100,np.uint8);path=tmp_path/'first.png';Image.fromarray(data).save(path)
    engine.send(cmd='load_image',path=str(path),device='cpu',strength=0)
    image=engine.wait_for('image_ready',timeout=60);document=image['load_id']
    engine.send(cmd='levels',action='set',spec=recipe(),document_id=document,gesture_id='one',request_id='levels-1')
    receipt=engine.wait_for('levels_result',timeout=30)
    assert receipt['success'] and receipt['request_id']=='levels-1' and receipt['document_id']==document
    admission=config();admission['max_address_bytes']=8*1024**3
    engine.send(cmd='inspection_snapshot',action='start',request_id='1',max_asset_bytes=1024*1024,render=admission)
    while True:
        event=engine.next_event(timeout=75)
        assert event['event']!='error',event
        if event['event']=='inspection_snapshot':
            assert event['state'] not in ('failed','cancelled','cancelling'),event
            if event['state']=='ready':result=Path(event['result_path']);break
    packet=result.read_bytes();assert packet[:4]==b'LRIF'
    pixels=np.frombuffer(packet[128:],np.uint8).reshape(7,8,4)
    expected=np.rint(L.levels_np(data.astype(np.float32)/255,recipe())*255).astype(np.uint8)
    np.testing.assert_allclose(pixels[:,:,:3],expected[3:10,2:10],rtol=0,atol=1)
    engine.send(cmd='inspection_snapshot',action='release',request_id='1')
    engine.wait_for('inspection_snapshot',timeout=10)
    engine.send(cmd='history',action='undo')
    assert L.is_identity(engine.wait_for('history_state',timeout=30)['doc_state']['levels'])
    other=tmp_path/'second.png';Image.fromarray(data).save(other)
    engine.send(cmd='load_image',path=str(other),device='cpu',strength=0)
    current=engine.wait_for('image_ready',timeout=60);assert current['load_id']!=document
    engine.send(cmd='levels',action='set',spec=recipe(),document_id=document,request_id='stale')
    while True:
        event=engine.next_event(timeout=20)
        if event['event']=='levels_result':break
    assert not event['success'] and event['document_id']==current['load_id']
    assert L.is_identity(event['spec'])


def test_failed_switch_invalidates_old_token_before_recipe_replacement(monkeypatch, tmp_path):
    from types import SimpleNamespace
    source = tmp_path / "new-photo.png"
    source.write_bytes(b"source identity fixture; decoding is mocked")
    from lumaretouch_engine import server,decode
    e=server.Engine('levels-switch-failure');e._load_id='old-document'
    events=[];installs=[]
    monkeypatch.setattr(server,'emit',events.append)
    monkeypatch.setattr(decode,'load_rgb',lambda *a,**k:SimpleNamespace(src_w=16,src_h=12))
    monkeypatch.setattr(e,'_remember_current',lambda:None)
    monkeypatch.setattr(e,'_effective_device',lambda:'cpu')
    def fail_attach(*a,**k):raise RuntimeError('injected attach failure')
    monkeypatch.setattr(e,'_open_session',fail_attach)
    with pytest.raises(RuntimeError,match='injected attach failure'):
        e.cmd_load_image({'path':str(source)})
    assert e._load_id=='' and e.doc_state()['document_id']==''
    monkeypatch.setattr(e,'_guard_editable',lambda name:None)
    e.cmd_levels({'action':'set','spec':recipe(),'document_id':'old-document','request_id':'stale'})
    assert events[-1]['event']=='levels_result' and not events[-1]['success']
    assert events[-1]['document_id']=='' and L.is_identity(e._levels)
    e.cmd_curves({'action':'clear','document_id':'old-document','request_id':'stale-curve'})
    assert events[-1]['event']=='curves_result' and not events[-1]['success']


def test_decode_failure_does_not_invalidate_current_document(monkeypatch, tmp_path):
    source = tmp_path / "bad-photo.png"
    source.write_bytes(b"source identity fixture; decoder rejects it")
    from lumaretouch_engine import server,decode
    e=server.Engine('levels-decode-failure');e._load_id='still-current'
    events=[]
    monkeypatch.setattr(server,'emit',events.append)
    monkeypatch.setattr(e,'_effective_device',lambda:'cpu')
    def fail_decode(*a,**k):raise ValueError('decode rejected')
    monkeypatch.setattr(decode,'load_rgb',fail_decode)
    e.cmd_load_image({'path':str(source)})
    assert 'decode rejected' in events[-1]['error']
    assert e._load_id=='still-current'
