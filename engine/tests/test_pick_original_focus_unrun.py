"""AUTHORED / UNRUN. Synthetic source contract fixtures, not photo acceptance.

Do not execute in the source-only task. Real RAW/ICC/device/performance review
requires the separately authorized validator and originals owned by that task.
"""
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import pick_original_focus as F, pick_focus_host as H


@pytest.mark.parametrize('point,expected', [((0, 0), (0, 0, 256, 256)),
    ((1, 1), (744, 544, 256, 256)), ((.5, .5), (371, 271, 256, 256))])
def test_native_grid_crop_is_bounded_not_resampled(point, expected):
    assert F.crop_rect(1000, 800, point) == expected
    assert F.crop_rect(10, 7, point) == (0, 0, 10, 7)


@pytest.mark.parametrize('bad', [True, float('nan'), float('inf'), -.1, 1.1, '0.5'])
def test_point_refuses_nonfinite_and_boolean(bad):
    with pytest.raises(ValueError):
        F.point(bad, .5)


def test_flat_crop_is_uninformative_not_a_blur_verdict():
    value = F.measures(np.full((32, 32, 3), .5, dtype=np.float32))
    assert value['low_contrast'] and value['detail_to_contrast'] is None
    assert value['laplacian_variance'] == 0
    assert not {'blur', 'best', 'rating', 'flag'} & value.keys()


def test_detail_reading_is_local_not_a_quality_probability():
    pattern = np.indices((32, 32)).sum(axis=0) % 2
    rgb = np.repeat(pattern[:, :, None], 3, axis=2).astype(np.float32)
    value = F.measures(rgb)
    assert value['laplacian_variance'] > 0
    assert value['detail_to_contrast'] > 1  # deliberately not probability [0,1]


@pytest.mark.parametrize('rgb', [np.zeros((300, 3, 3), dtype=np.float32),
    np.zeros((8, 8, 3), dtype=np.uint8), np.full((8, 8, 3), np.nan, dtype=np.float32)])
def test_measurements_refuse_unbounded_or_lower_precision_inputs(rgb):
    with pytest.raises(ValueError):
        F.measures(rgb)


def test_visible_drops_known_stale_crop_without_mutating_original(tmp_path):
    from lumaretouch_engine.local_mask_state import file_stamp
    path = tmp_path/'source.bin'
    path.write_bytes(b'original')
    row = {'path': str(path), 'pick_focus': {'source_stamp': list(file_stamp(path))}}
    assert F.visible(row)[0] is row['pick_focus']
    path.write_bytes(b'changed source')
    assert F.visible(row)[0] is None
    assert path.read_bytes() == b'changed source'


def test_selection_identity_reorder_rejects_before_worker(monkeypatch):
    row = {'document_id': 'current', 'path': '/not-opened'}
    engine = SimpleNamespace(_docs=[row], _doclock=threading.Lock(), _picks=None,
                             _pick_stop=threading.Event())
    events = []
    H.start(engine, {'cmd': 'pick', 'action': 'focus', 'indices': [0],
                    'focus_documents': ['stale']}, events.append)
    assert events[0]['event'] == 'pick_failed'
    assert events[0]['action'] == 'focus'
    assert engine._picks is None
    assert set(row) == {'document_id', 'path'}


def test_row_removed_or_same_path_replacement_cannot_receive_result():
    row = {'path': '/same', 'label': 'manual', 'tags': ['keep']}
    replacement = dict(row)
    engine = SimpleNamespace(_docs=[replacement], _doclock=threading.Lock())
    assert not H._write(engine, row, '/same', pick_focus={'version': 1})
    assert 'pick_focus' not in replacement
    assert replacement['label'] == 'manual' and replacement['tags'] == ['keep']


def test_success_final_state_is_not_worker_running(monkeypatch):
    monkeypatch.setattr(threading.current_thread(), "_lrt_focus_terminal", False, raising=False)
    row = {'path': '/original', 'label': 'manual', 'tags': ['keep']}
    states, events = [], []
    engine = SimpleNamespace(_docs=[row], _doclock=threading.Lock(),
        _picks=threading.current_thread(), _pick_stop=threading.Event())
    engine.emit_session_state = lambda **kw: states.append(kw.get("picks_running", True))
    monkeypatch.setattr(F, 'review', lambda *a, **kw: {'version': 1})
    H._loop(engine, [(row, '/original', None)], (.5, .5), events.append)
    assert events[-1]['event'] == 'pick_done' and events[-1]['count'] == 1
    assert states[-1] is False
    assert engine._picks is threading.current_thread()  # reservation held through publication
    assert row['label'] == 'manual' and row['tags'] == ['keep']


def test_terminal_wire_state_retains_admission_reservation():
    worker = SimpleNamespace(_lrt_original_focus=True, _lrt_focus_terminal=True, is_alive=lambda: True)
    engine = SimpleNamespace(_picks=worker)
    assert H.active(engine)
    assert not H.running(engine)
