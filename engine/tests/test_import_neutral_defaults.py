"""P0 enabled=false / strength=0: importing is not consent to beautify."""
import numpy as np
import pytest
from PIL import Image
from test_protocol import engine
from test_export import src
from test_acceptance_p1 import _current,_cmd_frame
from lumaretouch_engine.shm import FrameShm


def test_new_import_is_neutral_and_switching_restores_own_strength(engine,tmp_path):
    pytest.importorskip('torch')
    a,b=tmp_path/'a.png',tmp_path/'b.png'
    aa=src(80,96);bb=np.flip(aa,axis=1).copy()
    Image.fromarray(aa).save(a);Image.fromarray(bb).save(b)
    engine.send(cmd='hello');engine.wait_for('ready')
    engine.send(cmd='set_device',device='cpu');engine.wait_for('device_set')
    engine.send(cmd='load_image',path=str(a))
    shm=engine.wait_for('shm_ready',timeout=60);opened=engine.wait_for('image_ready',timeout=60)
    assert opened['doc_state']['strength']==0
    peer=FrameShm(shm['name'])
    try:
        np.testing.assert_array_equal(_current(engine,peer,80,96),aa)
        changed=_cmd_frame(engine,peer,80,96,cmd='set_strength',value=.6)
        assert np.any(changed!=aa)
        engine.send(cmd='load_image',path=str(b));opened=engine.wait_for('image_ready',timeout=60)
        assert opened['doc_state']['strength']==0
        np.testing.assert_array_equal(_current(engine,peer,80,96),bb)
        engine.send(cmd='load_image',path=str(a));opened=engine.wait_for('image_ready',timeout=60)
        assert opened['doc_state']['strength']==.6
        np.testing.assert_array_equal(_current(engine,peer,80,96),changed)
    finally:peer.close()
