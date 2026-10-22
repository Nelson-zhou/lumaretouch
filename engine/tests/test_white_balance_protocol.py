"""Actual engine WB preset/history/project/export round trip on synthetic RGB."""
import copy
import json
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from test_protocol import engine, _wait_frame_mode, _hist, _create_and_save, _collect_until
from lumaretouch_engine.shm import FrameShm
from lumaretouch_engine import white_balance_recipe as W
from lumaretouch_engine.scope import OP_WHITE_BALANCE


@pytest.fixture
def wb_engine(tmp_path, monkeypatch, request):
    monkeypatch.setenv('LRT_PRESET_DIR', str(tmp_path/'presets'))
    return request.getfixturevalue('engine')


def test_wb_real_pixels_preset_undo_project_and_export(wb_engine,tmp_path):
    pytest.importorskip('torch')
    e=wb_engine;source=tmp_path/'wb.png'
    Image.fromarray(np.full((64,64,3),[100,120,140],np.uint8)).save(source)
    e.send(cmd='load_image',path=str(source),device='cpu',strength=0)
    shm=e.wait_for('shm_ready',timeout=60);image=e.wait_for('image_ready',timeout=60)
    peer=FrameShm(shm['name'])
    def pixels():return np.frombuffer(peer.read_snapshot()[1],np.uint8).reshape(64,64,4).copy()
    try:
        base=pixels();options={**W.default_options(W.CORRECTED),'picked_gains':[1.2,.8,1.1]}
        e.send(cmd='exposure',wb_options=options)
        _wait_frame_mode(e,'exposure');edited=pixels()
        assert np.any(edited!=base) and _hist(e)['doc_state']['exposure']['lit']
        e.send(cmd='preset',action='save',id='wb',name='WB',module_scope=[OP_WHITE_BALANCE],request_id='save',document_id=image['load_id'])
        saved=e.wait_for('preset_saved',timeout=30)
        assert saved['preset']['modules'][OP_WHITE_BALANCE]['options']['picked_gains']==[1.2,.8,1.1]
        assert e.wait_for('preset_result',timeout=30)['success']
        e.send(cmd='exposure',action='clear');_wait_frame_mode(e,'exposure')
        np.testing.assert_array_equal(pixels(),base)
        before=_hist(e)
        e.send(cmd='preset',action='apply',id='wb',request_id='apply',document_id=image['load_id'])
        result=e.wait_for('preset_result',timeout=30);assert result['success']
        assert result['doc_state']['history']['undo_steps']==before['undo_steps']+1
        np.testing.assert_array_equal(pixels(),edited)
        e.send(cmd='history',action='undo');e.wait_for('history_state',timeout=30)
        np.testing.assert_array_equal(pixels(),base)
        e.send(cmd='history',action='redo');e.wait_for('history_state',timeout=30)
        np.testing.assert_array_equal(pixels(),edited)
        _,saved_project=_create_and_save(e,tmp_path)
        document=json.loads(Path(saved_project['path']).read_text());assert document['schema_version']=='lrt.project.v2'
        bad=copy.deepcopy(document);inactive=copy.deepcopy(bad['docs'][0]['versions'][0]);inactive['id']='bad-inactive'
        inactive['recipe']['_wb_options']['algorithm']='unknown';bad['docs'][0]['versions'].append(inactive)
        bad_path=tmp_path/'bad.json';bad_path.write_text(json.dumps(bad))
        before=_hist(e)
        e.send(cmd='project',action='open',path=str(bad_path),force=True)
        assert 'white-balance' in e.wait_for('error',timeout=30)['error']
        assert _hist(e)['doc_state']['exposure']==before['doc_state']['exposure']
        np.testing.assert_array_equal(pixels(),edited)
        inactive['recipe']['_wb_options']={**W.default_options(W.CORRECTED),'picked_gains':[1e308,1,1]}
        inactive['recipe']['_exposure']=[5,0,0,0,0,0,0]
        bad_path.write_text(json.dumps(bad))
        e.send(cmd='project',action='open',path=str(bad_path),force=True)
        assert e.wait_for('error',timeout=30)['error']
        assert _hist(e)['doc_state']['exposure']==before['doc_state']['exposure']
        np.testing.assert_array_equal(pixels(),edited)
        e.send(cmd='exposure',action='clear');_wait_frame_mode(e,'exposure')
        e.send(cmd='project',action='open',path=saved_project['path'],force=True)
        e.wait_for('project_opened',timeout=60)
        ready=e.wait_for('image_ready',timeout=60)
        assert ready['doc_state']['exposure']['options']==options
        np.testing.assert_array_equal(pixels(),edited)
        e.send(cmd='export',out_dir=str(tmp_path/'output'),format='png',tile=256)
        _collect_until(e,'export_done')
        exported=np.asarray(Image.open(tmp_path/'output'/'wb.png').convert('RGB'))
        assert np.max(np.abs(exported.astype(int)-edited[:,:,:3].astype(int)))<=1
    finally:
        peer.close()
