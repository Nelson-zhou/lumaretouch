"""AUTHORED / UNRUN: source-paint requests are read-only, never live brush writes.

Synthetic orchestration seams only. No pixel quality or runtime acceptance.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from test_spill_review_unrun import target, preview_request, apply_request
from lumaretouch_engine import spill_removal_controller as C
from lumaretouch_engine import spill_removal_paint_source as P
from lumaretouch_engine import project_recovery_runtime as RECOVERY


def source_request(engine, ident='paint-source'):
    request = preview_request(engine, ident)
    return {**{key: request[key] for key in C.BASE}, 'action': 'id_spill_paint_source'}


def test_source_read_has_no_fence_history_or_frame_and_replays_receipt(target, monkeypatch):
    engine, control, events, renders = target
    calls = []
    def prepare(request):
        calls.append(request)
        return {'token': 'a'*32, 'display_only': True}
    monkeypatch.setattr(P, 'owner', lambda engine: SimpleNamespace(prepare=prepare))
    before = deepcopy((engine._history_capture(), vars(engine.ledger)))
    request = source_request(engine)
    control.handle(request); control.handle(request)
    assert len(calls) == 1 and events[-1]['success'] and events[-1]['replayed']
    assert engine.fences == engine.frames == engine.cancellations == 0 and renders == []
    assert (engine._history_capture(), vars(engine.ledger)) == before


def test_new_source_read_expires_only_old_source_png_receipt(target, monkeypatch):
    engine, control, events, _ = target
    monkeypatch.setattr(P, 'owner', lambda engine: SimpleNamespace(prepare=lambda request: {'token':request['request_id']}))
    control.handle(source_request(engine, 'source-1'))
    control.cache['apply'] = ('digest', {'action':'id_spill_apply','success':True})
    control.cache['review'] = ('digest', {'action':'id_spill_preview','review':{'retained':True}})
    control.handle(source_request(engine, 'source-2'))
    assert 'paint_source' not in control.cache['source-1'][1]
    assert control.cache['source-1'][1]['outcome_unknown'] is False
    assert control.cache['apply'][1]['success']
    assert control.cache['review'][1]['review'] == {'retained':True}


@pytest.mark.parametrize('failed', [False, True])
def test_source_read_cannot_dirty_recovery_even_when_decode_refused(target, failed):
    engine, _, _, _ = target
    runtime = SimpleNamespace(revision=9, tainted=False, reason=None)
    engine._project_recovery_runtime = runtime
    boundary = {'message':source_request(engine), 'started':True, 'returned':not failed, 'failed':failed}
    RECOVERY.finish(engine, boundary, 'Source refused' if failed else None)
    assert vars(runtime) == {'revision':9, 'tainted':False, 'reason':None}


def test_only_preview_may_carry_paint_draft_and_transport_stays_bounded(target):
    engine, _, _, _ = target
    request = preview_request(engine)
    request.update(paint={'token':'a'*32, 'strokes':[]}, coverage_reviewed=True)
    C.envelope(request)
    with pytest.raises(ValueError): C.envelope({**source_request(engine), 'paint':request['paint']})
    with pytest.raises(ValueError): C.envelope({**request, 'unreviewed_pixels':[]})
    with pytest.raises(ValueError): C.envelope({**request, 'paint':{'token':'a'*32,'strokes':['x'*65536]}})
