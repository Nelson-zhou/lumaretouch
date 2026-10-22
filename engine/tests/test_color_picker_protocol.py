"""Real JSON-lines capture/probe/commit/history/project/export acceptance candidates.

These synthetic checks are authored, not executed locally. They do not replace
native presentation-proof, user interaction or photographic acceptance.
"""
import base64
import io
import uuid
import numpy as np
import pytest
from PIL import Image
from test_protocol import engine, _hist, _create_and_save, _collect_until
from lumaretouch_engine.shm import FrameShm

@pytest.fixture
def picker_engine(tmp_path,monkeypatch,request):
    root=tmp_path/'captures';root.mkdir(mode=0o700)
    monkeypatch.setenv('LRT_INSPECTION_ROOT',str(root))
    return request.getfixturevalue('engine')

@pytest.mark.parametrize('action,delta',[('levels_black',0.),('levels_white',0.),('curve',0.1),('hsl',15.)])
def test_real_action_probe_single_undo_project_and_full_export(picker_engine,tmp_path,action,delta):
    pytest.importorskip('torch')
    e=picker_engine;source=tmp_path/'color-pick.png'
    pixels=np.broadcast_to(np.array([130,100,60],np.uint8),(64,64,3)).copy()
    Image.fromarray(pixels).save(source)
    e.send(cmd='load_image',path=str(source),device='cpu',strength=0)
    shared=e.wait_for('shm_ready',timeout=60);image=e.wait_for('image_ready',timeout=60);document=image['load_id']
    peer=FrameShm(shared['name'])
    def view():return np.frombuffer(peer.read_snapshot()[1],np.uint8).reshape(64,64,4).copy()
    try:
        original=view();history=_hist(e);capture=uuid.uuid4().hex
        e.send(cmd='color_picker_capture',action='arm',capture_id=capture,ticket='1',document_id=document,
               epoch='a'*32,picker_action=action,picker_channel='master')
        armed=e.wait_for('color_picker_capture',timeout=30);assert armed['success'],armed
        descriptor=armed['descriptor'];assert descriptor['domain']=='color-action-input'
        packet=next((tmp_path/'captures').glob('lumaretouch-color-picker-*/capture.lrcp')).read_bytes()
        assert packet[:4]==b'LRCP' and len(packet)==128+64*64*4
        e.send(cmd='color_picker_capture',action='presented',capture_id=capture,ticket='1',document_id=document,generation=descriptor['generation'])
        assert e.wait_for('color_picker_capture',timeout=30)['success']
        proof={k:descriptor[k] for k in ('document_id','capture_id','ticket','generation','recipe_document_id','recipe_revision')}
        parameters=dict(action=action,channel='master',region={'x':30,'y':30,'width':5,'height':5},delta=delta,**proof)
        e.send(cmd='color_picker_probe',request_id='probe',**parameters)
        proposal=e.wait_for('color_picker_probe_result',timeout=30);assert proposal['success'],proposal
        preview=np.asarray(Image.open(io.BytesIO(base64.b64decode(proposal['preview']['data']))))
        assert preview.shape==(64,64,3);np.testing.assert_array_equal(view(),original)
        e.send(cmd='color_picker',request_id='apply',**parameters)
        receipt=e.wait_for('color_picker_result',timeout=30);assert receipt['success'],receipt
        assert receipt['history']['undo_steps']==history['undo_steps']+1
        edited=view();assert np.any(edited!=original)
        e.send(cmd='history',action='undo');e.wait_for('history_state',timeout=30)
        np.testing.assert_array_equal(view(),original)
        e.send(cmd='history',action='redo');e.wait_for('history_state',timeout=30)
        np.testing.assert_array_equal(view(),edited)
        _,saved=_create_and_save(e,tmp_path)
        e.send(cmd='project',action='open',path=saved['path'],force=True)
        e.wait_for('project_opened',timeout=60);e.wait_for('image_ready',timeout=60)
        np.testing.assert_array_equal(view(),edited)
        e.send(cmd='export',out_dir=str(tmp_path/'output'),format='png',tile=256)
        _collect_until(e,'export_done')
        exported=np.asarray(Image.open(tmp_path/'output'/'color-pick.png').convert('RGB'))
        assert np.max(np.abs(exported.astype(int)-edited[:,:,:3].astype(int)))<=1
        assert not list((tmp_path/'captures').glob('lumaretouch-color-picker-*'))
    finally:peer.close()
