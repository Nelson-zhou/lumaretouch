"""Correlated preset operations, compatibility, fencing and history finalization."""
from copy import deepcopy
from dataclasses import replace
import json
import pytest
from lumaretouch_engine import preset_controller as P, preset_store as PS, scope as S
from lumaretouch_engine.hsl_recipe import default_recipe, NEUTRAL


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv('LRT_PRESET_DIR', str(tmp_path/'presets'))
    state = {'_hsl': NEUTRAL, '_exposure': (0.,)*7}; document = ['doc-1']; events = []; invalid = []
    def replay(value, **kw):
        state.clear(); state.update(deepcopy(value)); return {'event': 'frame', 'render_ms': 1, 'mode': kw['mode']}
    c = P.PresetController(P.PresetPorts(lambda _: None, lambda: document[0], lambda: deepcopy(state),
        replay, lambda: ('ok', ''), lambda: {'document_id': document[0], 'hsl': list(state['_hsl'])},
        lambda: invalid.append(True)), events.append)
    return c, state, document, events, invalid


def send(c, events, action='save', request='r1', **values):
    p = {'cmd': 'preset', 'action': action, 'request_id': request, **values}
    c.handle_command(p); c.finish(p)
    assert events[-1]['event'] == 'preset_result' and events[-1]['request_id'] == request
    return events[-1]


def save_args(**extra):
    return {'id': 'custom', 'name': '婚纱暖调', 'module_scope': [S.OP_HSL], 'document_id': 'doc-1', **extra}


def test_save_is_deferred_until_finish_and_returns_actual_file(setup):
    c, state, _, events, _ = setup; state['_hsl'] = (20.,) + NEUTRAL[1:]
    p = {'action': 'save', 'request_id': 'save', **save_args()}
    c.handle_command(p)
    assert events[-1]['event'] == 'preset_saved' and not any(e['event'] == 'preset_result' for e in events)
    c.finish(p); result = events[-1]
    assert result['success'] and not result['outcome_unknown'] and result['module_scope'] == [S.OP_HSL]
    assert PS.load_file(result['path'])['modules'][S.OP_HSL]['recipe']['bands'][0] == 20


@pytest.mark.parametrize('patch', [
    {'module_scope': []}, {'module_scope': {S.OP_HSL: False}}, {'module_scope': [True]},
    {'module_scope': None}, {'document_id': 'old'}, {'document_id': None},
    {'force': 'false'}, {'name': '  '}, {'name': 123}, {'name': '名'*81}, {'name': 'name\x1c'}, {'unused': 1},
])
def test_invalid_correlated_save_is_definite_rejection(setup, patch):
    c, _, _, events, _ = setup
    result = send(c, events, **save_args(**patch))
    assert not result['success'] and not result['outcome_unknown']
    assert not any(e['event'] == 'preset_saved' for e in events)


@pytest.mark.parametrize('action', [float('nan'), float('inf'), {'bad': 1}, '\ud800'])
def test_malformed_action_still_has_serializable_terminal_receipt(setup, action):
    c, _, _, events, _ = setup
    result = send(c, events, action=action)
    assert not result['success'] and not result['outcome_unknown']
    json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')


def test_same_request_replays_after_document_switch_and_changed_payload_rejects(setup):
    c, state, document, events, _ = setup
    first = send(c, events, **save_args()); document[0] = 'doc-2'
    repeated = send(c, events, **save_args())
    assert repeated['success'] and repeated['replayed'] and repeated['path'] == first['path']
    assert len([e for e in events if e['event'] == 'preset_saved']) == 1
    changed = send(c, events, **save_args(name='different'))
    assert not changed['success'] and not changed['outcome_unknown']
    assert PS.find('custom')['name'] == '婚纱暖调'
    stale = send(c, events, request='new', **save_args(id='stale'))
    assert not stale['success'] and not stale['outcome_unknown']


def test_list_and_file_actions_do_not_require_a_loaded_photo(setup):
    c, _, document, events, _ = setup; document[0] = ''
    c.ports = replace(c.ports, guard=lambda _: 'no image')
    result = send(c, events, action='list')
    assert result['success'] and result['catalog']['available']
    assert not send(c, events, action='delete', request='delete', id='portrait-soft')['success']


def test_directory_read_failure_is_not_empty_success(setup, monkeypatch):
    c, _, _, events, _ = setup
    def fail(): raise PermissionError('denied')
    monkeypatch.setattr(PS, 'list_all', fail)
    result = send(c, events, action='list')
    assert not result['success'] and not result['outcome_unknown']
    assert next(e for e in events if e['event'] == 'preset_list')['errors']


def test_receipt_cache_bounds_and_legacy_save(setup, monkeypatch):
    c, _, _, events, _ = setup; monkeypatch.setattr(P, 'MAX_RECEIPTS', 2)
    for i in range(3): assert send(c, events, action='list', request=str(i))['success']
    assert len(c._receipts) == 2 and '0' not in c._receipts
    legacy = {'action': 'save', **save_args()}; legacy.pop('document_id')
    c.handle_command(legacy)
    assert events[-1]['event'] == 'preset_saved'


@pytest.mark.parametrize('rollback_fails', [False, True])
def test_apply_reports_rollback_outcome(setup, rollback_fails):
    c, state, _, events, invalid = setup
    state['_hsl'] = (20.,) + NEUTRAL[1:]; assert send(c, events, **save_args())['success']; state['_hsl'] = NEUTRAL
    real = c.ports.replay
    def replay(value, **kw):
        if kw['mode'] == 'preset' or rollback_fails: raise RuntimeError('render failure')
        return real(value, **kw)
    c.ports = replace(c.ports, replay=replay)
    result = send(c, events, action='apply', request='apply', id='custom', document_id='doc-1')
    assert not result['success'] and result['outcome_unknown'] == rollback_fails
    assert result['requires_reload'] == rollback_fails and bool(invalid) == rollback_fails


@pytest.mark.parametrize('correlated', [False, True])
def test_dispatcher_records_separate_fast_applications_and_receipt_after_history(monkeypatch, correlated):
    from lumaretouch_engine import server
    e = server.Engine('preset-history'); events = []; monkeypatch.setattr(server, 'emit', events.append)
    e._load_id = 'doc'; e._guard_editable = lambda _: None; e.HISTORY_GROUP_MS = 10**9
    e.doc_state = lambda: {'document_id': e._load_id, 'history': e._history_report()}
    def find(pid):
        r = default_recipe(); r['bands'][0] = 20. if pid == 'a' else 30.
        return {'id': pid, 'name': pid, 'kind': 'custom', 'modules': {S.OP_HSL: {'recipe': r}}}
    monkeypatch.setattr(PS, 'find', find)
    def replay(state, **kw): e._apply_state(state); return {'event': 'frame', 'render_ms': 1}
    e._replay_state = replay
    messages = []
    for index, pid in enumerate(('a', 'b')):
        p = {'cmd': 'preset', 'action': 'apply', 'id': pid, '_host_request_id': index + 1}
        if correlated: p.update(request_id=pid, document_id='doc')
        messages.append(p); e._process_line(json.dumps(p), {'preset': e.cmd_preset})
        assert e._history_report()['undo_steps'] == index + 1
        assert events[-1]['event'] == 'command_done'
        if correlated:
            result = events[-2]; assert result['event'] == 'preset_result' and result['success']
            assert result['doc_state']['history']['undo_steps'] == index + 1
    if correlated:
        e._process_line(json.dumps(messages[0]), {'preset': e.cmd_preset})
        assert events[-2]['replayed'] and e._hsl[0] == 30 and e._history_report()['undo_steps'] == 2


def test_history_failure_changes_success_into_uncertainty(setup):
    c, state, _, events, _ = setup
    p = {'action': 'save', 'request_id': 'save', **save_args()}
    c.handle_command(p); c.finish(p, 'history bookkeeping failed')
    assert not events[-1]['success'] and events[-1]['outcome_unknown']
    assert PS.find('custom')['name'] == '婚纱暖调'


def test_wire_ascii_byte_limit_and_cache_byte_eviction(setup, monkeypatch):
    c, _, _, events, _ = setup
    c.state = lambda: {'available': True, 'list': [{'name': '中'*100}], 'errors': [], 'modules': []}
    first = send(c, events, action='list')
    ascii_size = len(json.dumps(first, ensure_ascii=True).encode()) + 1
    utf8_size = len(json.dumps(first, ensure_ascii=False).encode()) + 1
    assert ascii_size > utf8_size
    monkeypatch.setattr(P, 'MAX_CACHE_BYTES', ascii_size + 20)
    assert send(c, events, action='list', request='r2')['success']
    assert 'r1' not in c._receipts and 'r2' in c._receipts
    monkeypatch.setattr(P, 'MAX_RESULT_BYTES', (ascii_size + utf8_size)//2)
    result = send(c, events, action='list', request='r3')
    assert result['error_code'] == 'receipt_too_large' and not result['outcome_unknown']


@pytest.mark.parametrize('unknown,committed', [(False, False), (True, None), (True, True)])
def test_storage_outcome_fields_survive_controller(setup, monkeypatch, unknown, committed):
    c, _, _, events, _ = setup
    def fail(*args, **kwargs): raise PS.PresetStorageError('injected', outcome_unknown=unknown, committed=committed)
    monkeypatch.setattr(PS, 'save', fail)
    result = send(c, events, **save_args())
    assert not result['success'] and result['outcome_unknown'] == unknown
    assert result['operation_committed'] is committed


def test_successful_import_and_delete_report_real_ids_and_paths(setup, tmp_path):
    c, _, _, events, _ = setup
    path = tmp_path/'external.json'
    path.write_text(S.dump_preset({'schema': S.PRESET_SCHEMA, 'id': 'imported', 'name': '外部', 'kind': 'custom',
                                  'modules': {S.OP_HSL: {'recipe': default_recipe()}}}), encoding='utf-8')
    imported = send(c, events, action='import', path=str(path))
    assert imported['success'] and imported['id'] == 'imported' and PS.find('imported')['name'] == '外部'
    deleted = send(c, events, action='delete', request='delete', id='imported')
    assert deleted['success'] and deleted['path'] == imported['path']
    with pytest.raises(S.ScopeError): PS.find('imported')
