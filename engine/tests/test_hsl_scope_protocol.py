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


@pytest.mark.parametrize('correlated', [False, True])
def test_hsl_scoped_preset_pixels_one_step_undo_and_project(hsl_engine, tmp_path, correlated):
    pytest.importorskip('torch')
    engine = hsl_engine
    path = tmp_path/'colors.png'; Image.fromarray(np.full((64, 64, 3), [160, 75, 45], np.uint8)).save(path)
    engine.send(cmd='load_image', path=str(path), device='cpu', strength=0)
    shm = engine.wait_for('shm_ready', timeout=60); image = engine.wait_for('image_ready', timeout=60)
    document = image['load_id']
    peer = FrameShm(shm['name'])
    def pixels(): return np.frombuffer(peer.read_snapshot()[1], np.uint8).reshape(64, 64, 4).copy()
    try:
        engine.send(cmd='exposure', ev=.25); _wait_frame_mode(engine, 'exposure'); baseline = pixels()
        engine.send(cmd='hsl', action='set', band=0, dh=20, ds=-15, dl=10)
        _wait_frame_mode(engine, 'hsl'); edited = pixels(); assert np.any(edited != baseline)
        save_identity = {'request_id': 'save', 'document_id': document} if correlated else {}
        engine.send(cmd='preset', action='save', id='hsl-colors', name='测试调色', module_scope=[OP_HSL], **save_identity)
        saved = engine.wait_for('preset_saved', timeout=30)
        assert list(saved['preset']['modules']) == [OP_HSL]
        if correlated:
            receipt = engine.wait_for('preset_result', timeout=30)
            assert receipt['success'] and receipt['request_id'] == 'save' and receipt['document_id'] == document
        engine.send(cmd='hsl', action='clear'); _wait_frame_mode(engine, 'hsl')
        np.testing.assert_array_equal(pixels(), baseline); before = _hist(engine)
        apply_identity = {'request_id': 'apply', 'document_id': document} if correlated else {}
        engine.send(cmd='preset', action='apply', id='hsl-colors', **apply_identity)
        applied = engine.wait_for('preset_applied', timeout=30); _wait_frame_mode(engine, 'preset')
        assert applied['modules'] == [OP_HSL]
        if correlated:
            receipt = engine.wait_for('preset_result', timeout=30)
            assert receipt['success'] and receipt['doc_state']['history']['undo_steps'] == before['undo_steps'] + 1
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
        if correlated:
            engine.send(cmd='preset', action='apply', id='hsl-colors', request_id='stale', document_id=document)
            assert '照片已经变化' in engine.wait_for('error', timeout=30)['error']
            rejected = engine.wait_for('preset_result', timeout=30)
            assert rejected['request_id'] == 'stale' and not rejected['success'] and not rejected['outcome_unknown']
            engine.send(cmd='hsl', action='clear'); _wait_frame_mode(engine, 'hsl')
            engine.send(cmd='preset', action='apply', id='hsl-colors', **apply_identity)
            assert engine.wait_for('preset_result', timeout=30)['replayed']
            np.testing.assert_array_equal(pixels(), baseline)
    finally:
        peer.close()


def test_preset_catalog_import_copy_conflict_and_delete_without_photo(hsl_engine, tmp_path):
    """Actual no-photo commands and disk effects, including protected/duplicate IDs."""
    pytest.importorskip('torch')
    import json
    from pathlib import Path
    from lumaretouch_engine.hsl_recipe import default_recipe
    from lumaretouch_engine.scope import PRESET_SCHEMA
    engine = hsl_engine
    engine.send(cmd='hello')
    assert engine.wait_for('ready')['preset_result_protocol'] == 1

    def command(request, action, *, rejected=False, **values):
        engine.send(cmd='preset', action=action, request_id=request, **values)
        if rejected:
            assert engine.wait_for('error', timeout=30)['error'].startswith('preset ')
        result = engine.wait_for('preset_result', timeout=30)
        assert result['request_id'] == request and result['action'] == action
        assert result['success'] is (not rejected) and not result['outcome_unknown']
        return result

    original = command('list-original', 'list')['catalog']
    builtin = next(p['id'] for p in original['list'] if p['builtin'])
    source = tmp_path/'external.json'
    source.write_text(json.dumps({'schema': PRESET_SCHEMA, 'id': 'imported', 'name': '未载图导入',
        'kind': 'custom', 'modules': {OP_HSL: {'recipe': default_recipe()}}}), encoding='utf-8')
    imported = command('import', 'import', path=str(source))
    installed = Path(imported['path']); before = installed.read_bytes()
    assert imported['id'] == 'imported' and imported['module_scope'] == [OP_HSL]
    assert '已存在' in command('conflict', 'import', path=str(source), rejected=True)['error']
    assert installed.read_bytes() == before
    copied = command('copy', 'import', path=str(source), id='copied')
    assert copied['id'] == 'copied' and Path(copied['path']).is_file()
    assert '内置' in command('protect-builtin', 'delete', id=builtin, rejected=True)['error']
    catalog = command('list-imported', 'list')['catalog']
    assert {'imported', 'copied'}.issubset({p['id'] for p in catalog['list']})
    deleted = command('delete', 'delete', id='imported')
    assert deleted['path'] == str(installed) and not installed.exists()
    assert '没有这个预设文件' in command('missing', 'delete', id='imported', rejected=True)['error']
    remaining = command('list-final', 'list')['catalog']
    ids = {p['id'] for p in remaining['list']}
    assert 'imported' not in ids and 'copied' in ids and builtin in ids
