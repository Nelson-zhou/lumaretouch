import numpy as np
import pytest
from PIL import Image
from test_protocol import engine,_wait_frame_mode,_hist
from lumaretouch_engine.shm import FrameShm


def test_compare_original_bypasses_all_edits_without_mutating_recipe(engine,tmp_path):
    pytest.importorskip('torch')
    y,x=np.mgrid[:90,:120];source=np.stack([(x*3+y)%256,(x+y*2)%256,(x*2+y*3)%256],axis=-1).astype(np.uint8)
    path=tmp_path/'original.png';Image.fromarray(source).save(path)
    engine.send(cmd='hello');engine.wait_for('ready')
    engine.send(cmd='set_device',device='cpu');engine.wait_for('device_set')
    engine.send(cmd='load_image',path=str(path),strength=0)
    shm=engine.wait_for('shm_ready',timeout=60);engine.wait_for('image_ready',timeout=60)
    peer=FrameShm(shm['name'])
    try:
        engine.send(cmd='exposure',ev=.4);_wait_frame_mode(engine,'exposure')
        edited=np.frombuffer(peer.read_snapshot()[1],np.uint8).reshape(90,120,4)[...,:3]
        assert np.any(edited!=source)
        state=_hist(engine)
        engine.send(cmd='compare',on=True,capture_id='capture-regression')
        receipt=engine.wait_for('frame',timeout=60)
        assert receipt['capture_id']=='capture-regression' and receipt['doc']==str(path)
        assert receipt['view']=='original'
        actual=np.frombuffer(peer.read_snapshot()[1],np.uint8).reshape(90,120,4)[...,:3]
        np.testing.assert_array_equal(actual,source)
        engine.send(cmd='compare',on=False);engine.wait_for('frame',timeout=60)
        actual=np.frombuffer(peer.read_snapshot()[1],np.uint8).reshape(90,120,4)[...,:3]
        np.testing.assert_array_equal(actual,edited)
        after=_hist(engine)
        assert after['doc_state']==state['doc_state'] and after['undo_steps']==state['undo_steps']
        for bad in ('false',0,1,None):
            engine.send(cmd='compare',on=bad)
            error=engine.wait_for('error',timeout=30)
            assert 'boolean' in error['error']
            untouched=np.frombuffer(peer.read_snapshot()[1],np.uint8).reshape(90,120,4)[...,:3]
            np.testing.assert_array_equal(untouched,edited)
    finally:peer.close()


@pytest.mark.parametrize('layer',['exposure','lut','repair','crop','combined'])
def test_original_view_bypasses_each_pixel_layer_and_preserves_cache(layer):
    pytest.importorskip('torch')
    from lumaretouch_engine.vram import PreviewPipeline,RepairOp
    from lumaretouch_engine.ops.lut import bake
    y,x=np.mgrid[:80,:96];src=np.stack([(x*7+y*3)%256,(x*3+y*5)%256,(x*5+y*7)%256],axis=-1).astype(np.uint8)
    pipe=PreviewPipeline('cpu',96,80);pipe.load_rgb_u8(src)
    original=pipe.src_f32.clone()
    if layer in ('exposure','combined'):pipe.set_exposure(.4,0,0)
    if layer in ('lut','combined'):pipe.set_lut(bake(lambda x:np.clip(x*.7+.1,0,1),17))
    if layer in ('repair','combined'):
        mask=np.zeros((80,96),np.uint8);mask[20:35,30:45]=255
        pipe.set_repair_ops([RepairOp(1,mask)])
    if layer in ('crop','combined'):pipe.set_geometry((.1,.1,.8,.8),90)
    pipe.render(.5);edited=pipe.read_back().copy()
    assert np.any(edited[...,:3]!=src)
    key=pipe.filter_key;cached=pipe.retouched
    pipe.render_original()
    np.testing.assert_array_equal(pipe.read_back()[...,:3],src)
    assert np.all(pipe.read_back()[...,3]==255)
    assert pipe.filter_key==key and pipe.retouched is cached
    np.testing.assert_array_equal(pipe.src_f32.numpy(),original.numpy())
    pipe.render(.5)
    np.testing.assert_array_equal(pipe.read_back(),edited)
