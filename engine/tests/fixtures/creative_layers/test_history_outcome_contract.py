"""UNRUN authored fixtures: structured shared-history outcomes, no pixel oracle.

Qoder owns local execution. These ports simulate only transaction boundaries and
must not be presented as renderer/integration verification.
"""
from copy import deepcopy
from dataclasses import replace

from lumaretouch_engine.history_controller import HistoryController, HistoryPorts


def fixture():
    live = [{'_proxy': (10, 20), 'value': 2}]
    events, restores = [], []

    def restore(snapshot, mode):
        live[0] = deepcopy(snapshot)
        restores.append(mode)
        return {'event': 'frame', 'render_ms': 1}

    ports = HistoryPorts(
        capture=lambda: deepcopy(live[0]), signature=lambda value: repr(value),
        restore_frame=restore, guard=lambda action: None,
        remember_current=lambda: None, status=lambda: deepcopy(live[0]),
        mark_dirty=lambda: None)
    owner = HistoryController(ports, events.append, lambda: 1000, 3, 250)
    owner.undo = [{'_proxy': (10, 20), 'value': 1}]
    return owner, live, events, restores


def test_failed_restore_with_confirmed_rollback_is_rejected():
    owner, live, events, restores = fixture()
    original = owner.ports.restore_frame
    undo = deepcopy(owner.undo)

    def restore(snapshot, mode):
        if mode == 'history_undo':
            live[0] = {'partial': True}
            raise RuntimeError('restore fixture')
        return original(snapshot, mode)

    owner.ports = replace(owner.ports, restore_frame=restore)
    result = owner.handle_command({'cmd': 'history', 'action': 'undo'})
    assert result['status'] == 'rejected' and result['message']
    assert live[0]['value'] == 2 and owner.undo == undo and owner.redo == []
    assert restores == ['history_rollback']
    assert [event['event'] for event in events] == ['error']


def test_failed_restore_and_failed_rollback_are_unknown():
    owner, live, events, _ = fixture()

    def fail(snapshot, mode):
        live[0] = {'partial': mode}
        raise RuntimeError(mode)

    owner.ports = replace(owner.ports, restore_frame=fail)
    result = owner.handle_command({'cmd': 'history', 'action': 'undo'})
    assert result['status'] == 'unknown' and result['message']
    assert len(owner.undo) == 1 and owner.redo == []
    assert [event['event'] for event in events] == ['engine_warn', 'error']


def test_publication_failure_after_restore_is_unknown_not_no_change():
    owner, live, events, restores = fixture()

    def emit(event):
        if event['event'] == 'frame':
            raise RuntimeError('frame publication fixture')
        events.append(event)

    owner.emit = emit
    result = owner.handle_command({'cmd': 'history', 'action': 'undo'})
    assert result['status'] == 'unknown' and result['message']
    assert live[0]['value'] == 1 and owner.undo == [] and owner.redo[0]['value'] == 2
    assert restores == ['history_undo']
    assert [event['event'] for event in events] == ['history_state', 'error']


def test_empty_history_is_confirmed_no_change():
    owner, live, events, restores = fixture()
    owner.undo = []
    result = owner.handle_command({'cmd': 'history', 'action': 'undo'})
    assert result == {'status': 'no_change'}
    assert live[0]['value'] == 2 and owner.undo == [] and owner.redo == []
    assert restores == [] and events[-1]['noop'] is True


def test_failed_error_sink_still_returns_unknown_after_restore():
    owner, _, _, _ = fixture()

    def fail(event):
        raise RuntimeError('all publication unavailable')

    owner.emit = fail
    result = owner.handle_command({'cmd': 'history', 'action': 'undo'})
    assert result['status'] == 'unknown' and result['message']
