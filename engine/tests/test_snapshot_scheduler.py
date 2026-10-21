"""Real command sequencer: queued edits precede copy ticks and cancel old inputs."""
import os
import json
import threading
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import server
from lumaretouch_engine.render_snapshot import SnapshotTransaction


def harness():
    e = server.Engine.__new__(server.Engine)
    e._quit = False
    e.shm = None
    e.stop_flag = threading.Event()
    e.EDIT_CMDS = ()
    e._inspection_snapshot_tx = None
    e._inspection_snapshot_result = None
    e._inspection_snapshot_id = None
    e._inspection_snapshot_last_id = 0
    e._inspection_snapshot_state = 'idle'
    return e


def test_actual_run_prioritizes_edit_and_cancels_before_mutation(monkeypatch):
    e = harness(); source = np.arange(128, dtype=np.uint8); created = []; events = []
    read_fd, write_fd = os.pipe()
    input_stream = os.fdopen(read_fd, 'r', encoding='utf-8')
    os.write(write_fd, (json.dumps({'cmd': 'start', '_host_request_id': 'one'})+'\n').encode())
    monkeypatch.setattr(server.sys, 'stdin', input_stream)
    monkeypatch.setattr(server, 'emit', events.append)
    def start(_):
        tx = SnapshotTransaction({'source': source}, max_asset_bytes=128)
        created.append(tx); e._inspection_snapshot_tx = tx
        e._inspection_snapshot_id = '1'; e._inspection_snapshot_state = 'copying'
    def edit(_):
        assert e._inspection_snapshot_tx is None
        assert created[0]._cancelled and created[0].copied_bytes == 16
        source[:] = 9
        e._command_inbox.put_nowait(json.dumps({'cmd': 'stop', '_host_request_id': 'three'}))
    def stop(_):
        e._quit = True
    e._dispatch_table = lambda: {'start': start, 'edit': edit, 'stop': stop}
    e.SNAPSHOT_TICK_BYTES = 16
    original_tick = e._tick_snapshot
    def tick():
        original_tick()
        e._command_inbox.put_nowait(json.dumps({'cmd': 'edit', '_host_request_id': 'two'}))
    e._tick_snapshot = tick
    try:
        e.run()
    finally:
        os.close(write_fd)
        input_stream.close()
    assert (source == 9).all() and e.stop_flag.is_set()
    assert e._inspection_snapshot_result is None
    assert [v['request_id'] for v in events if v['event'] == 'command_done'] == ['one','two','three']
    assert not any(v.get('state') == 'ready' for v in events)


def test_eof_cleans_pending_or_completed_snapshot(monkeypatch):
    e = harness(); e._inspection_snapshot_tx = SnapshotTransaction({'a': np.ones(8,np.uint8)},max_asset_bytes=8)
    e._dispatch_table = lambda: {}
    read_fd, write_fd = os.pipe()
    os.close(write_fd)
    with os.fdopen(read_fd, 'r', encoding='utf-8') as input_stream:
        monkeypatch.setattr(server.sys, 'stdin', input_stream)
        monkeypatch.setattr(server, 'emit', lambda _: None)
        e.run()
    assert e._inspection_snapshot_tx is None and e._inspection_snapshot_result is None
    assert e.stop_flag.is_set()


def test_preparation_command_owns_assets_and_checks_request_identity(monkeypatch):
    e = harness(); events = []; source = np.arange(32,dtype=np.uint8)
    e._image_loaded = True; e._vram = SimpleNamespace(h=4,w=8); e._doc_path = '/fixture.png'
    e._export = e.bench = None
    e._capture_state = lambda: {'source': source}
    def translate(state, **options):
        assert options == dict(device='cpu',scale=1,upscale_backend='lanczos3',sharpen=0)
        return state
    e._state_to_export_snap = translate
    monkeypatch.setattr(server, 'emit', events.append)
    e.cmd_inspection_snapshot({'action':'start','request_id':'9007199254740993','max_asset_bytes':32})
    assert e._inspection_snapshot_state == 'copying'
    e._tick_snapshot()
    assert e._inspection_snapshot_state == 'ready'
    assert events[-1]['preparation_only'] is True and events[-1]['asset_bytes'] == 32
    assert not np.shares_memory(e._inspection_snapshot_result.value['source'], source)
    with pytest.raises(ValueError, match='identity'):
        e.cmd_inspection_snapshot({'action':'cancel','request_id':'2'})
    assert e._inspection_snapshot_result is not None
    with pytest.raises(ValueError, match='increase'):
        e.cmd_inspection_snapshot({'action':'start','request_id':'9007199254740993','max_asset_bytes':32})
    e.cmd_inspection_snapshot({'action':'release','request_id':'9007199254740993'})
    assert e._inspection_snapshot_result is None and e._inspection_snapshot_state == 'released'


def test_command_ack_survives_malformed_and_unknown_commands(monkeypatch):
    e = harness(); events = []; monkeypatch.setattr(server,'emit',events.append)
    e._process_line('{bad', {})
    e._process_line(json.dumps({'cmd':'unknown','_host_request_id':'id'}), {})
    assert events[-1] == {'event':'command_done','request_id':'id'}
    assert len([v for v in events if v['event']=='error']) == 2

from test_protocol import engine


def test_real_engine_ack_precedes_snapshot_ready_and_edit_invalidates(engine, tmp_path):
    pytest.importorskip('torch')
    from PIL import Image
    path = tmp_path/'input.png'
    Image.fromarray(np.full((64, 96, 3), 100, np.uint8)).save(path)
    engine.send(cmd='load_image', path=str(path), device='cpu', strength=0)
    engine.wait_for('image_ready', timeout=60)
    engine.send(cmd='inspection_snapshot', action='start', request_id='1',
                max_asset_bytes=1024*1024, _host_request_id='snapshot-accepted')
    seen = []
    while True:
        event = engine.next_event(timeout=20)
        seen.append(event)
        assert event['event'] != 'error', event
        if event['event'] == 'inspection_snapshot' and event['state'] == 'ready':
            break
    assert any(v.get('event') == 'command_done' and v.get('request_id') == 'snapshot-accepted' for v in seen[:-1])
    assert seen[-1]['preparation_only'] is True
    engine.send(cmd='exposure', ev=.2)
    invalidated = engine.wait_for('inspection_snapshot', timeout=20)
    assert invalidated['state'] == 'cancelled' and invalidated['request_id'] == '1'


def test_shutdown_exits_normally_while_parent_keeps_stdin_open(engine):
    engine.send(cmd='hello')
    engine.wait_for('ready', timeout=30)
    engine.send(cmd='shutdown')
    assert not engine.proc.stdin.closed
    assert engine.proc.wait(timeout=5) == 0


def test_reader_initialization_failure_still_cleans_resources(monkeypatch):
    e = harness(); e._dispatch_table = lambda: {}; closed = []
    e.shm = SimpleNamespace(close=lambda: closed.append('close'), unlink=lambda: closed.append('unlink'))
    e._inspection_snapshot_tx = SnapshotTransaction({'a': np.ones(8,np.uint8)},max_asset_bytes=8)
    def bad_fd():
        raise OSError('injected bad stdin')
    monkeypatch.setattr(server.sys, 'stdin', SimpleNamespace(fileno=bad_fd))
    with pytest.raises(OSError):
        e.run()
    assert e._inspection_snapshot_tx is None and e.stop_flag.is_set()
    assert closed == ['close','unlink'] and e._command_inbox is None


def test_eof_executes_last_utf8_command_without_newline(monkeypatch):
    e = harness(); seen = []
    def stop(message):
        seen.append(message['name']); e._quit = True
    e._dispatch_table = lambda: {'stop': stop}
    read_fd, write_fd = os.pipe()
    os.write(write_fd, json.dumps({'cmd':'stop','name':'照片'},ensure_ascii=False).encode('utf-8'))
    os.close(write_fd)
    with os.fdopen(read_fd, 'r', encoding='utf-8') as stream:
        monkeypatch.setattr(server.sys,'stdin',stream)
        monkeypatch.setattr(server,'emit',lambda _:None)
        e.run()
    assert seen == ['照片']


def test_shutdown_with_command_backlog_does_not_wait_for_queue_drain(engine):
    engine.send(cmd='hello'); engine.wait_for('ready', timeout=30)
    engine.proc.stdin.write('{"cmd":"shutdown"}\n' + '{"cmd":"hello"}\n'*100)
    engine.proc.stdin.flush()
    assert engine.proc.wait(timeout=5) == 0


def test_reader_decode_error_is_reported_and_releases_snapshot(monkeypatch):
    e = harness(); e._dispatch_table = lambda: {}; seen = []
    e._inspection_snapshot_tx = SnapshotTransaction({'a':np.ones(8,np.uint8)},max_asset_bytes=8)
    read_fd, write_fd = os.pipe(); os.write(write_fd,b'\xff\n'); os.close(write_fd)
    with os.fdopen(read_fd,'r',encoding='utf-8') as stream:
        monkeypatch.setattr(server.sys,'stdin',stream)
        monkeypatch.setattr(server,'emit',seen.append)
        e.run()
    assert any(v.get('event')=='error' and v['error'].startswith('stdin:') for v in seen)
    assert e._inspection_snapshot_tx is None and e._inspection_snapshot_result is None


def test_copy_failure_does_not_block_next_command(monkeypatch):
    e = harness(); seen = []
    e._inspection_snapshot_tx = SnapshotTransaction({'a':np.ones(8,np.uint8)},max_asset_bytes=8)
    e._inspection_snapshot_id = '1'; e._inspection_snapshot_state = 'copying'
    def failing_tick():
        raise MemoryError('injected copy failure')
    e._tick_snapshot = failing_tick
    def stop(_):
        e._quit = True
    e._dispatch_table = lambda: {'stop':stop}
    read_fd, write_fd = os.pipe()
    def emit(value):
        seen.append(value)
        if value.get('state')=='failed':
            os.write(write_fd,b'{"cmd":"stop","_host_request_id":"after-failure"}\n')
    with os.fdopen(read_fd,'r',encoding='utf-8') as stream:
        monkeypatch.setattr(server.sys,'stdin',stream)
        monkeypatch.setattr(server,'emit',emit)
        try:
            e.run()
        finally:
            os.close(write_fd)
    assert any(v.get('request_id')=='after-failure' and v['event']=='command_done' for v in seen)
    assert e._inspection_snapshot_tx is None and e._inspection_snapshot_result is None
