"""Actual command, disk, pixels, history and project round-trip for HSL scope."""
import numpy as np
import pytest
from PIL import Image
from test_protocol import engine, _wait_frame_mode, _hist, _create_and_save
from lumaretouch_engine.shm import FrameShm
from lumaretouch_engine.scope import OP_HSL


@pytest.fixture
def hsl_engine(tmp_path, monkeypatch, request):
    monkeypatch.setenv('LRT_PRESET_DIR', str(tmp_path/'presets'))
    return request.getfixturevalue('engine')


def test_hsl_scoped_preset_pixels_one_step_undo_and_project(hsl_engine, tmp_path):
    pytest.importorskip('torch')
    engine = hsl_engine
    path = tmp_path/'colors.png'; Image.fromarray(np.full((64, 64, 3), [160, 75, 45], np.uint8)).save(path)
    engine.send(cmd='load_image', path=str(path), device='cpu', strength=0)
    shm = engine.wait_for('shm_ready', timeout=60); engine.wait_for('image_ready', timeout=60)
    peer = FrameShm(shm['name'])
    def pixels(): return np.frombuffer(peer.read_snapshot()[1], np.uint8).reshape(64, 64, 4).copy()
    try:
        engine.send(cmd='exposure', ev=.25); _wait_frame_mode(engine, 'exposure'); baseline = pixels()
        engine.send(cmd='hsl', action='set', band=0, dh=20, ds=-15, dl=10)
        _wait_frame_mode(engine, 'hsl'); edited = pixels(); assert np.any(edited != baseline)
        engine.send(cmd='preset', action='save', id='hsl-colors', module_scope=[OP_HSL])
        saved = engine.wait_for('preset_saved', timeout=30)
        assert list(saved['preset']['modules']) == [OP_HSL]
        engine.send(cmd='hsl', action='clear'); _wait_frame_mode(engine, 'hsl')
        np.testing.assert_array_equal(pixels(), baseline); before = _hist(engine)
        engine.send(cmd='preset', action='apply', id='hsl-colors')
        applied = engine.wait_for('preset_applied', timeout=30); _wait_frame_mode(engine, 'preset')
        assert applied['modules'] == [OP_HSL]
        after = _hist(engine); assert after['undo_steps'] == before['undo_steps'] + 1
        assert after['doc_state']['exposure'] == before['doc_state']['exposure']
        np.testing.assert_array_equal(pixels(), edited)
        engine.send(cmd='history', action='undo'); engine.wait_for('history_state', timeout=30)
        np.testing.assert_array_equal(pixels(), baseline)
        engine.send(cmd='history', action='redo'); engine.wait_for('history_state', timeout=30)
        np.testing.assert_array_equal(pixels(), edited)
        _, project = _create_and_save(engine, tmp_path)
        engine.send(cmd='hsl', action='clear'); _wait_frame_mode(engine, 'hsl')
        engine.send(cmd='project', action='open', path=project['path'], force=True)
        engine.wait_for('project_opened', timeout=60)
        assert _hist(engine)['doc_state']['hsl']['bands'][:3] == [20., -15., 10.]
        np.testing.assert_array_equal(pixels(), edited)
    finally:
        peer.close()
