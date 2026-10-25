"""Protocol/cancellation source fixtures. UNRUN, no runtime pass is asserted."""
import json
from types import SimpleNamespace
from lumaretouch_engine import background_material_host as H


def request(ident='bg-1'):
    return {'cmd': 'background_material_library', 'action': 'request', 'request_id': ident,
            'request': {'method': 'command', 'op': 'group_create', 'payload': {'name': 'A'}, 'expected_revision': 0}}


def test_cancel_before_reader_registration_prevents_dispatch(monkeypatch):
    host = H.BackgroundMaterialHost(); called = []; results = []
    monkeypatch.setattr(H, 'dispatch', lambda *a, **k: called.append(True))
    assert host.observe_line(json.dumps({'cmd': 'background_material_library_cancel', 'request_id': 'bg-1'}))
    assert not host.observe_line(json.dumps(request()))
    host.handle(SimpleNamespace(), request(), results.append)
    assert not called and results[0]['error_code'] == 'cancelled'
    assert results[0]['committed'] is False and not results[0]['outcome_unknown']


def test_durable_success_survives_late_cancel_and_replays_without_dispatch(monkeypatch):
    host = H.BackgroundMaterialHost(); called = []; results = []
    def dispatch(*args, **kwargs):
        called.append(True); host.cancel('bg-1')
        return {'version': 1, 'changed': True, 'revision': 1}
    monkeypatch.setattr(H, 'dispatch', dispatch)
    host.handle(SimpleNamespace(), request(), results.append)
    host.handle(SimpleNamespace(), request(), results.append)
    assert len(called) == 1 and results[0] == results[1]
    assert results[0]['success'] and results[0]['committed'] and not results[0]['outcome_unknown']


def test_conflicting_request_cannot_overwrite_original_terminal(monkeypatch):
    host = H.BackgroundMaterialHost(); results = []
    monkeypatch.setattr(H, 'dispatch', lambda *a, **k: {'changed': True, 'revision': 1})
    original = request(); host.handle(SimpleNamespace(), original, results.append)
    changed = request(); changed['request']['payload']['name'] = 'B'
    host.handle(SimpleNamespace(), changed, results.append)
    host.handle(SimpleNamespace(), original, results.append)
    assert results[1]['error_code'] == 'request_conflict' and results[0] == results[2]


def test_cancel_tombstone_overflow_fails_closed(monkeypatch):
    host = H.BackgroundMaterialHost(); called = []; results = []
    monkeypatch.setattr(H, 'dispatch', lambda *a, **k: called.append(True))
    for number in range(H.MAX_RECORDS + 1): host.cancel('cancel-' + str(number))
    host.handle(SimpleNamespace(), request('later'), results.append)
    assert not called and results[0]['error_code'] == 'cancelled'


def test_reader_never_runs_image_or_catalogue_work(monkeypatch):
    host = H.BackgroundMaterialHost(); called = []
    monkeypatch.setattr(H, 'dispatch', lambda *a, **k: called.append(True))
    assert not host.observe_line(json.dumps(request()))
    assert not called and 'bg-1' in host.events


def test_outer_guard_rejection_is_known_not_applied_and_retires_ingress(monkeypatch):
    engine = SimpleNamespace(); host = H.BackgroundMaterialHostMixin._background_material_host(engine)
    called = []; results = []
    monkeypatch.setattr(H, 'dispatch', lambda *a, **k: called.append(True))
    host.observe_line(json.dumps(request()))
    H.dispatch_rejected(engine, request(), 'another operation is active', False, results.append)
    assert not called and 'bg-1' not in host.events
    assert not results[0]['success'] and not results[0]['outcome_unknown']
    assert results[0]['committed'] is False and results[0]['error_code'] == 'dispatch_rejected'
    host.handle(engine, request(), results.append)
    assert not called and results[1] == results[0]


def test_outer_error_after_entry_without_terminal_is_retained_unknown(monkeypatch):
    engine = SimpleNamespace(); host = H.BackgroundMaterialHostMixin._background_material_host(engine)
    called = []; results = []
    monkeypatch.setattr(H, 'dispatch', lambda *a, **k: called.append(True))
    host.register('bg-1')
    H.dispatch_rejected(engine, request(), 'interrupted after entry', True, results.append)
    assert results[0]['outcome_unknown'] and results[0]['committed'] is None
    assert results[0]['error_code'] == 'dispatch_unknown' and not host.events
    host.handle(engine, request(), results.append)
    assert not called and results[1] == results[0]


def test_outer_rejection_preserves_matching_authoritative_success(monkeypatch):
    engine = SimpleNamespace(); host = H.BackgroundMaterialHostMixin._background_material_host(engine)
    called = []; results = []
    def dispatch(*args, **kwargs):
        called.append(True); return {'changed': True, 'revision': 1}
    monkeypatch.setattr(H, 'dispatch', dispatch)
    host.handle(engine, request(), results.append)
    host.register('bg-1')
    H.dispatch_rejected(engine, request(), 'later guard failed', True, results.append)
    assert len(called) == 1 and results[1] == results[0]
    assert results[1]['success'] and results[1]['committed'] and not host.events


def test_outer_conflicting_rejection_cannot_replace_original_receipt(monkeypatch):
    engine = SimpleNamespace(); host = H.BackgroundMaterialHostMixin._background_material_host(engine)
    results = []
    monkeypatch.setattr(H, 'dispatch', lambda *a, **k: {'changed': True, 'revision': 1})
    original = request(); host.handle(engine, original, results.append)
    changed = request(); changed['request']['payload']['name'] = 'different'
    H.dispatch_rejected(engine, changed, 'blocked', False, results.append)
    assert results[1]['error_code'] == 'request_conflict'
    H.dispatch_rejected(engine, original, 'blocked again', False, results.append)
    assert results[2] == results[0]


def test_outer_rejections_are_bounded_and_release_cancel_tombstones(monkeypatch):
    engine = SimpleNamespace(); host = H.BackgroundMaterialHostMixin._background_material_host(engine)
    called = []; results = []
    monkeypatch.setattr(H, 'dispatch', lambda *a, **k: called.append(True))
    for number in range(H.MAX_RECORDS + 20):
        ident = 'rejected-' + str(number); host.cancel(ident)
        H.dispatch_rejected(engine, request(ident), 'blocked', False, results.append)
    assert not called and not host.events and not host.early_cancel
    assert len(host.results) <= H.MAX_RECORDS and host.retained_bytes <= H.MAX_RETAINED_BYTES
