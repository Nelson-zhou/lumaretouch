"""Derived masks may be rebuilt, but user channel/scope choices must survive."""
import numpy as np
import pytest
from lumaretouch_engine.server import Engine
from lumaretouch_engine.shm import FrameShm
from test_protocol import engine, _load, _create_and_save, _wait_frame_mode, _frame_of


@pytest.mark.parametrize('state',[{'_channel':'skin'},{'_grade_scope':'skin'}])
def test_mask_dependent_recipe_requests_reanalysis(state):
    assert Engine.__new__(Engine)._recipe_needs_landmarks({"_enhance": {"amounts": {}}, **state})


@pytest.mark.parametrize('skin_grade',[False,True])
def test_project_reopen_restores_masked_pixels(engine,tmp_path,skin_grade):
    pytest.importorskip("torch")
    meta=_load(engine,max_px=207360,strength=0.5)
    peer=FrameShm(meta['name'])
    try:
        engine.send(cmd='precompute',backend='synthetic')
        engine.wait_for('precompute_ready',timeout=30)
        engine.send(cmd='set_strength',value=0.65,channel='skin')
        frame=_wait_frame_mode(engine,'drag')
        if skin_grade:
            engine.send(cmd='grade',action='set',dv=0.15)
            _wait_frame_mode(engine,'grade')
            engine.send(cmd='grade',action='scope',scope='skin')
            frame=_wait_frame_mode(engine,'grade')
        saved=_frame_of(frame,peer,meta['h'],meta['w']).copy()
        _,project=_create_and_save(engine,tmp_path)
        engine.send(cmd='project',action='open',path=project['path'])
        engine.wait_for('project_opened',timeout=30)
        restored=_wait_frame_mode(engine,'precompute_restore',timeout=30)
        got=_frame_of(restored,peer,meta['h'],meta['w'])
        assert np.array_equal(got,saved),'reopening changed the masked edit pixels'
        engine.send(cmd='history',action='state')
        state=engine.wait_for('history_state')['doc_state']
        assert state['channel']=='skin'
        assert state['grade']['scope']==('skin' if skin_grade else 'all')
    finally:
        peer.close()
