"""AUTHORED / UNRUN. No application imports or test execution in source-only pass.

Fixtures are simulated contract inputs, NOT real detector/image acceptance.
Run only in Qoder's separately authorized local verification, after native build.
"""
from copy import deepcopy
import hashlib
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from lumaretouch_engine import picks as PK
from lumaretouch_engine import pick_group_eye as GE
from lumaretouch_engine import pick_group_eye_host as HOST


@pytest.fixture
def measured(tmp_path):
    source, model = tmp_path / 'source.jpg', tmp_path / 'face_landmarker.task'
    source.write_bytes(b'not-an-image-contract-fixture')
    model.write_bytes(b'not-a-model-contract-fixture')
    m = PK.Measures(path=str(source), eye_open=.1, faces=4, ratio=.4,
                    contrast=.2, sharpness=.1, decode_size=(512, 256),
                    decoded_from='decoded_proxy', source_stamp=PK.source_stamp(str(source)))
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    pc = SimpleNamespace(backend='mediapipe', manual=(), num_faces=4,
                         all_landmarks=[np.zeros((478, 3)) for _ in range(4)],
                         detection_limit=32, detection_limit_reached=False,
                         detector_model_sha256=digest)
    fn = SimpleNamespace(name='mediapipe', model_paths={'face_landmarker.task': str(model)},
                         detector_model_sha256=digest)
    m.face_detection = GE.capture(pc, fn, m)
    return m, source, model, pc, fn


def suggestion(m):
    result = PK.suggest(m, group=[m.path], is_leader=False, rank_in_group=0, dup_bits=None,
                        user_marked=True)
    result.update(fingerprint=PK.fingerprint(), edge=512, model_dir=None)
    return result


def test_old_settings_default_off_and_strict_input_unrun():
    assert GE.settings() == {'version': 1, 'more_than': None}
    for value in ({}, {'version': 2, 'more_than': 3}, {'version': True, 'more_than': 3},
                  {'version': 1, 'more_than': True}, {'version': 1, 'more_than': 0},
                  {'version': 1, 'more_than': 32}, {'version': 1, 'more_than': 3.0},
                  {'version': 1, 'more_than': 3, 'laughter': True}):
        with pytest.raises(ValueError): GE.settings(value)


def test_same_native_detection_provenance_and_no_metadata_fallback_unrun(measured):
    m, _, _, pc, fn = measured
    assert GE.current(m) == 4
    assert m.face_detection['eye_open'] == m.eye_open
    assert m.face_detection['source_stamp'] == m.source_stamp
    pc.num_faces = 5
    assert GE.capture(pc, fn, m) == {}
    pc.num_faces, pc.backend = 4, 'synthetic'
    assert GE.capture(pc, fn, m) == {}
    m.face_detection = {}
    m.faces = 32  # stale legacy metadata MUST NOT enable the exception
    assert GE.decision(m, {'version': 1, 'more_than': 3}) == 'unknown'


@pytest.mark.parametrize('change', ['source', 'model', 'aperture', 'dimensions', 'sha', 'missing'])
def test_stale_evidence_does_not_reach_native_unrun(measured, monkeypatch, change):
    m, source, model, _, _ = measured
    if change == 'source': source.write_bytes(b'replaced-original')
    if change == 'model': model.write_bytes(b'replaced-detector')
    if change == 'aperture': m.eye_open = .05
    if change == 'dimensions': m.decode_size = (256, 128)
    if change == 'sha': m.face_detection['detector_sha256'] = '0' * 64
    if change == 'missing': m.face_detection = {}
    monkeypatch.setattr(GE, 'native', lambda: pytest.fail('must not evaluate stale count'))
    assert GE.decision(m, {'version': 1, 'more_than': 3}) == 'unknown'


def test_optional_native_unavailable_keeps_existing_hint_unrun(measured, monkeypatch):
    m, *_ = measured
    def missing(): raise OSError('native absent')
    monkeypatch.setattr(GE, 'native', missing)
    value = PK.reapply_eye_rule(suggestion(m), m.path, {'version': 1, 'more_than': 3})
    assert value['group_eye_rule_state'] == 'unavailable'
    assert 'eyes_closed' in value['labels']
    assert any(r['kind'] == 'eyes_rule_unknown' for r in value['reasons'])


def test_threshold_boundary_uses_real_rust_abi_unrun(measured):
    """Requires built library. Do not replace absent native with Python predicate."""
    m, *_ = measured
    GE.native()  # missing build fails loudly; fixture is not silently skipped
    for threshold, expected in [(3, 'omit'), (4, 'not_matched'), (5, 'not_matched')]:
        assert GE.decision(m, {'version': 1, 'more_than': threshold}) == expected


def test_rule_change_only_recomputes_eye_hints_and_never_passes_unrun(measured, monkeypatch):
    m, *_ = measured
    original = suggestion(m)
    # Mock only the Rust reply here; real boundary/ABI is covered separately above.
    monkeypatch.setattr(GE, 'native', lambda: SimpleNamespace(lrt_pick_group_eye_evaluate_v1=lambda *_: 3))
    omitted = PK.reapply_eye_rule(original, m.path, {'version': 1, 'more_than': 3})
    assert 'eyes_closed' not in omitted['labels']
    assert any(r['kind'] == 'eyes_omitted_by_rule' for r in omitted['reasons'])
    assert omitted['group_eye_rule_state'] == 'omit'
    assert omitted['measures'] == original['measures']
    restored = PK.reapply_eye_rule(omitted, m.path, None)
    assert 'eyes_closed' in restored['labels']
    for value in (original, omitted, restored):
        assert value['overridden_by_user'] and value['overridable']
        assert not value['auto_deleted'] and not value['auto_trashed']
        assert value['suggest'] in ('review', 'none')  # never keep/pass
    assert [r for r in original['reasons'] if not r['kind'].startswith('eyes_')] == [
        r for r in omitted['reasons'] if not r['kind'].startswith('eyes_')]


def test_no_failed_detection_stays_unknown_and_never_omitted_unrun(monkeypatch):
    m = PK.Measures(path='/missing', faces=32, eye_open=None, eye_note='Detection failed')
    monkeypatch.setattr(GE, 'native', lambda: pytest.fail('no verified count'))
    labels, reasons, state = PK.eye_hints(m, 'standard', {'version': 1, 'more_than': 3})
    assert state == 'unknown' and 'eyes_closed' not in labels
    assert any(r['kind'] == 'eyes_unknown' for r in reasons)
    assert not any(r['kind'] == 'eyes_omitted_by_rule' for r in reasons)


def test_legacy_cache_and_stale_display_are_invalidated_unrun(measured):
    m, source, _, _, _ = measured
    value = suggestion(m)
    old = {**value, 'fingerprint': 'v3'}
    assert not PK.reusable(old, m.path, 512, value['sensitivities'])
    with pytest.raises(ValueError): PK.reapply_eye_rule(old, m.path, None)
    source.write_bytes(b'replaced-original')
    assert PK.visible(value, m.path)[0] is None


def test_host_preserves_flags_selection_focus_and_source_unrun(measured, monkeypatch):
    m, source, _, _, _ = measured
    row = {'document_id': 'doc-1', 'path': m.path, 'pick': suggestion(m), 'tags': ['flag:accepted', 'rating:4'],
           'label': 'red', 'trashed': False, 'pick_focus': {'untouched': True}, 'state': {'edits': True}}
    before = deepcopy(row); source_before = source.read_bytes()
    engine = SimpleNamespace(_docs=[row], _doclock=threading.RLock(), _picks=None,
                             _doc_index=0, emit_session_state=lambda: None)
    from lumaretouch_engine import face
    monkeypatch.setattr(face, 'build', lambda *_: pytest.fail('cached-only must not construct detector'))
    events = []
    HOST.apply(engine, {'cmd': 'pick', 'action': 'group_rule', 'indices': [0],
                       'pick_documents': ['doc-1'], 'group_eye_rule': {'version': 1, 'more_than': None}}, events.append)
    assert events[-1]['cached_only'] and events[-1]['measured'] == 0
    for key in ('tags', 'label', 'trashed', 'state', 'pick_focus'): assert row[key] == before[key]
    assert engine._doc_index == 0 and source.read_bytes() == source_before
    before = deepcopy(row)
    HOST.apply(engine, {'cmd': 'pick', 'action': 'group_rule', 'indices': [0],
                       'pick_documents': ['wrong-document'], 'group_eye_rule': None}, events.append)
    assert events[-1]['event'] == 'pick_failed' and row == before
    engine._picks = SimpleNamespace(is_alive=lambda: True)
    HOST.apply(engine, {'cmd': 'pick', 'action': 'group_rule', 'indices': [0],
                       'pick_documents': ['doc-1'], 'group_eye_rule': None}, events.append)
    assert events[-1]['event'] == 'pick_failed' and row == before


def test_analyze_terminal_wire_does_not_release_actual_worker_admission_unrun():
    from lumaretouch_engine.pick_focus_host import running
    worker = SimpleNamespace(is_alive=lambda: True)
    engine = SimpleNamespace(_picks=worker)
    assert running(engine)
    worker._lrt_pick_terminal = True
    assert not running(engine)  # final session snapshot is no longer busy
    assert worker.is_alive()  # _start_picks/group_rule admission still rejects
    del worker._lrt_pick_terminal
    worker._lrt_focus_terminal = True
    assert not running(engine)  # existing focus terminal semantics are preserved


def test_nonfirst_copy_never_lends_rule_to_source_publisher_owner_unrun(measured):
    m, *_ = measured
    first = suggestion(m)
    first['sensitivities'] = {**first['sensitivities'], 'eyes': 'strong'}
    copy_cache = suggestion(m)
    copy_cache['group_eye_rule'] = {'version': 1, 'more_than': 3}
    copy_cache['group_eye_rule_state'] = 'omit'
    rows = [{'path': m.path, 'document_id': 'first', 'pick': first},
            {'path': m.path, 'document_id': 'copy', 'pick': copy_cache},
            {'path': '/unrelated', 'document_id': 'other', 'pick': None}]
    before = deepcopy(rows)
    pooled = [(p, owner['row'].get('pick')) for p, owner in PK.source_owners(rows, 'workspace').items()]
    assert pooled == [(m.path, first), ('/unrelated', None)]
    assert not PK.reusable(pooled[0][1], m.path, 512, copy_cache['sensitivities'])
    assert rows == before  # an incompatible first cache never promotes the copy
    rows[0]['pick'] = None
    assert PK.source_owners(rows, 'workspace')[m.path]['row']['pick'] is None
    assert rows[1]['pick'] is copy_cache  # copy retains its own independent rule


def test_exact_row_document_workspace_ownership_survives_only_reorder_unrun():
    first = {'document_id': 'first', 'path': '/same.jpg', 'pick': {'rule': 'off'}}
    second = {'document_id': 'second', 'path': '/other.jpg', 'pick': None}
    rows = [first, second]
    owner = PK.source_owners(rows, 'workspace-1')['/same.jpg']
    assert PK.owner_index(rows, 'workspace-1', owner) == 0
    assert PK.owner_index([second, first], 'workspace-1', owner) == 1
    assert PK.owner_index([dict(first), second], 'workspace-1', owner) == -1
    assert PK.owner_index(rows, 'workspace-2', owner) == -1
    first['document_id'] = 'replacement-id'
    assert PK.owner_index(rows, 'workspace-1', owner) == -1
    first['document_id'], first['path'] = 'first', '/relocated.jpg'
    assert PK.owner_index(rows, 'workspace-1', owner) == -1


def test_worker_publication_refuses_same_path_project_replacement_unrun():
    """Host method fixture; authorized validator may import engine, source pass did not."""
    from lumaretouch_engine.server import Engine
    from lumaretouch_engine import library_query_host as LQ
    old = {'document_id': 'doc', 'path': '/same.jpg', 'pick': {'old': True}, 'tags': ['flag:accepted']}
    engine = SimpleNamespace(_docs=[old], _doclock=threading.RLock())
    session = LQ.session_id(engine)
    owner = PK.source_owners(engine._docs, session)['/same.jpg']
    replacement = {**deepcopy(old), 'pick': {'new-project': True}}
    engine._docs = [replacement]  # same ID/path is still a different row owner
    before = deepcopy(replacement)
    for fields in ({'pick': {'new-measurement': True}},
                   {'pick': None, 'pick_error': 'failed'},
                   {'pick': None, 'pick_error': 'pooled-cache-invalid'}):
        assert Engine._pick_write(engine, '/same.jpg', owner=owner, **fields) == -1
        assert replacement == before
    engine._docs = [old]
    assert Engine._pick_write(engine, '/same.jpg', owner=owner, pick={'valid': True}) == 0
    assert old['pick'] == {'valid': True} and old['tags'] == ['flag:accepted']
