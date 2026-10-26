"""AUTHORED / UNRUN. Requires explicitly built native helpers and local engine.

Exercises the actual canonical source/Undo/Redo/project routes; the author has
not imported or run this module, engine, torch, helper or image operations.
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image
import pytest
from test_protocol import engine, _hist, _create_and_save, _wait_frame_mode


@pytest.mark.parametrize('algorithm', ['legacy-xyz-ratio-v1', 'linear-srgb-d-white-ratio-v1'])
@pytest.mark.parametrize('reference', [None, 7000.0])
def test_actual_auto_repeated_undo_redo_save_reopen_preserves_nullable_reference(engine, tmp_path, algorithm, reference):
    pytest.importorskip('torch')
    e = engine
    ready = e.wait_for('ready', timeout=60)
    assert ready['white_balance_auto_protocol'] == 1, 'Build matching Rust helper before this explicit local acceptance run'
    source = tmp_path/'auto-cast.png'
    Image.fromarray(np.full((64, 64, 3), [110, 135, 155], np.uint8)).save(source)
    e.send(cmd='load_image', path=str(source), device='cpu', strength=0)
    image = e.wait_for('image_ready', timeout=60)
    if reference is not None:
        e.send(cmd='exposure', reference_k=reference); _wait_frame_mode(e, 'exposure')
    if algorithm != 'legacy-xyz-ratio-v1':
        e.send(cmd='white_balance', action='set_algorithm', algorithm=algorithm, request_id='algorithm', document_id=image['load_id'])
        assert e.wait_for('white_balance_result', timeout=30)['success']
    before = _hist(e)['doc_state']
    assert before['exposure']['reference_k'] == reference
    e.send(cmd='white_balance', action='auto', request_id='auto-first', document_id=before['document_id'], **before['white_balance_auto_input'])
    result = e.wait_for('white_balance_result', timeout=30)
    assert result['success'] and result['phase'] == 'applied'
    after = result['after']; assert after['reference_k'] == reference
    assert after['options']['algorithm'] == algorithm and after['options']['picked_gains'] != [1., 1., 1.]
    e.send(cmd='history', action='undo')
    undone = e.wait_for('history_state', timeout=30)['doc_state']['exposure']
    assert undone == before['exposure'] and undone['reference_k'] == reference
    e.send(cmd='history', action='redo')
    redone = e.wait_for('history_state', timeout=30)['doc_state']['exposure']
    assert redone == after and redone['reference_k'] == reference
    _, saved = _create_and_save(e, tmp_path)
    project = json.loads(Path(saved['path']).read_text())
    def states(value):
        if isinstance(value, dict):
            if '_wb_options' in value: yield value
            for child in value.values(): yield from states(child)
        elif isinstance(value, list):
            for child in value: yield from states(child)
    assert any(s['_wb_options'] == after['options'] and s.get('_exposure_ref_k') == reference for s in states(project))
    e.send(cmd='project', action='open', path=saved['path'], force=True)
    e.wait_for('project_opened', timeout=60)
    reopened = e.wait_for('image_ready', timeout=60)['doc_state']
    assert reopened['exposure'] == after and reopened['exposure']['reference_k'] == reference
    e.send(cmd='white_balance', action='auto', request_id='auto-after-reopen', document_id=reopened['document_id'], **reopened['white_balance_auto_input'])
    repeat = e.wait_for('white_balance_result', timeout=30)
    assert repeat['success'] and repeat['no_change'] and repeat['after'] == after
    assert repeat['history'] == repeat['before_history']
