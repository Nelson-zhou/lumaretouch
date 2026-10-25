# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Receipt lifetime fixtures, no actual engine/image mutation."""
from types import SimpleNamespace
import pytest
from lumaretouch_engine import light_glow_host as H
from lumaretouch_engine import light_glow_stage as S


def command():
    return {'version': 1, 'operation_id': S.OPERATION, 'action': 'cancel',
            'request_id': 'cancel', 'session_id': 'session', 'token': None,
            'owner': {'document_id': 'document', 'document_epoch': 'epoch', 'document_revision': '4',
                      'source': {'sha256': 'a'*64, 'width': 4, 'height': 3, 'orientation': 'exif_normalized_once'}}}


def test_receipt_query_never_executes_an_unknown_write():
    service = H.Service(SimpleNamespace(), lambda event: None)
    result = service.receipt(command())
    assert result['phase'] == 'unknown' and result['outcome_unknown']
    assert not service.writes and service.uncertain is None


def test_same_write_replays_receipt_without_reexecuting(monkeypatch):
    service = H.Service(SimpleNamespace(), lambda event: None)
    calls = []
    def cancel(value):
        calls.append(value)
        return H._receipt(value, outcome='cancelled', message='fixture')
    monkeypatch.setattr(service, '_cancel', cancel)
    first = service.submit(command())
    second = service.submit(command())
    assert first == second and len(calls) == 1


def test_reused_identity_with_different_exact_content_is_refused():
    service = H.Service(SimpleNamespace(), lambda event: None)
    service._save(command(), H._receipt(command(), outcome='cancelled'))
    changed = command()
    changed['session_id'] = 'another'
    with pytest.raises(ValueError):
        service.submit(changed)


def test_entered_unknown_blocks_other_writes_and_cannot_be_cancelled():
    service = H.Service(SimpleNamespace(), lambda event: None)
    service.uncertain = {'command': {'request_id': 'previous'}}
    with pytest.raises(ValueError):
        service._cancel(command())
    with pytest.raises(ValueError):
        service._guard()
    service.maintain()
    assert service.uncertain is not None


def test_outer_never_started_rejection_settles_exact_write_receipt():
    engine = SimpleNamespace()
    events = []
    request = {'cmd': 'light_glow', 'action': 'submit', 'request_id': 'cancel', 'command': command()}
    H.dispatch_rejected(request, 'blocked fixture', False, events.append, engine=engine)
    result = events.pop()
    assert set(result) == {'event', 'request_id', 'status', 'receipt'}
    assert result['receipt']['phase'] == 'done' and result['receipt']['outcome'] == 'rejected'
    assert H.service(engine, events.append).receipt(command()) == result['receipt']


def test_write_capacity_never_evicts_original_unknown_proof(monkeypatch):
    service = H.Service(SimpleNamespace(), lambda event: None)
    original = command()
    service._save(original, H._receipt(original, phase='unknown'))
    monkeypatch.setattr(H, 'MAX_WRITES', 1)
    other = {**original, 'request_id': 'other'}
    with pytest.raises(ValueError):
        service.submit(other)
    assert service._known(original)['phase'] == 'unknown'
