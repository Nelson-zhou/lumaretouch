import numpy as np
import pytest
from PIL import Image
from test_protocol import engine, _wait_frame_mode, _hist, _create_and_save
from lumaretouch_engine.shm import FrameShm
from lumaretouch_engine.ops.curves import default_curves


def test_curves_pixels_history_project_and_original(engine,tmp_path):
    pytest.importorskip('torch')
    src=np.full((64,64,3),64,np.uint8);path=tmp_path/'curve-source.png';Image.fromarray(src).save(path)
    engine.send(cmd='hello');engine.wait_for('ready')
    engine.send(cmd='load_image',path=str(path),device='cpu',strength=0)
    shm=engine.wait_for('shm_ready',timeout=60);engine.wait_for('image_ready',timeout=60)
    peer=FrameShm(shm['name'])
    def pixels():return np.frombuffer(peer.read_snapshot()[1],np.uint8).reshape(64,64,4).copy()
    try:
        baseline=pixels()
        spec=default_curves();spec['red']=[[0,.1],[1,1]]
        engine.send(cmd='curves',action='set',spec=spec,gesture_id='drag-1');_wait_frame_mode(engine,'curves')
        first=pixels();assert np.any(first[...,0]!=baseline[...,0])
        spec['red']=[[0,.2],[1,1]]
        engine.send(cmd='curves',action='set',spec=spec,gesture_id='drag-1');_wait_frame_mode(engine,'curves')
        edited=pixels();state=_hist(engine);assert state['undo_steps']==1
        engine.send(cmd='compare',on=True);engine.wait_for('frame',timeout=30)
        np.testing.assert_array_equal(pixels(),baseline)
        engine.send(cmd='compare',on=False);engine.wait_for('frame',timeout=30)
        np.testing.assert_array_equal(pixels(),edited)
        engine.send(cmd='history',action='undo');engine.wait_for('history_state',timeout=30)
        np.testing.assert_array_equal(pixels(),baseline)
        engine.send(cmd='history',action='redo');engine.wait_for('history_state',timeout=30)
        np.testing.assert_array_equal(pixels(),edited)
        _,project=_create_and_save(engine,tmp_path)
        engine.send(cmd='curves',action='clear');_wait_frame_mode(engine,'curves')
        # This test intentionally discards its own temporary clear operation.
        engine.send(cmd='project',action='open',path=project['path'],force=True);engine.wait_for('project_opened',timeout=60)
        engine.send(cmd='history',action='state');restored=engine.wait_for('history_state',timeout=30)
        assert restored['doc_state']['curves']==spec
        np.testing.assert_array_equal(pixels(),edited)
    finally:peer.close()
