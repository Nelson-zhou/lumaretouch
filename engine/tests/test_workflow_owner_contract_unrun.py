"""Authored but NOT executed in the source-only automation development pass.

These isolated contract fixtures are not product-runtime acceptance evidence.
"""
from copy import deepcopy
import hashlib
import uuid
from types import SimpleNamespace
import pytest
from lumaretouch_engine import workflow_owner_protocol as P
from lumaretouch_engine import workflow_owner_host as H
from lumaretouch_engine import workflow_owner_export as E


def uid():
    return str(uuid.uuid4())


def graph(preset=False):
    nodes = [
        {'id': 'watch', 'error_policy': 'stop', 'operation': {
            'kind': 'directory_source', 'root': '/watch', 'recursive': False,
            'include_existing': False, 'extensions': ['jpg'], 'settle_ms': 500}},
        {'id': 'import', 'error_policy': 'stop', 'operation': {
            'kind': 'managed_import', 'project_id': 'project', 'project_path': '/project.lrt', 'managed_root': '/managed'}},
    ]
    if preset:
        nodes.append({'id': 'preset', 'error_policy': 'stop', 'operation': {
            'kind': 'compatible_preset', 'preset_id': 'color-warm', 'preset_sha256': 'a' * 64, 'when_all_labels': []}})
    nodes.append({'id': 'export', 'error_policy': 'stop', 'operation': {
        'kind': 'export', 'output_root': '/output', 'recipe_sha256': P.RECIPE_SHA256}})
    value = {'schema_version': 1, 'workflow_id': 'workflow', 'revision': 1, 'nodes': nodes,
             'edges': [{'from': a['id'], 'to': b['id']} for a, b in zip(nodes, nodes[1:])]}
    return value, hashlib.sha256(P.encoded(value)).hexdigest()


def document():
    return {'project_id': 'project', 'document_id': 'document', 'document_revision': '0',
            'source_sha256': 'a' * 64, 'receipt_id': uid()}


def command(doc=None, kind='freeze_export', plan=None):
    doc = doc or document()
    _, graph_sha = graph()
    identity = {'workflow_id': 'workflow', 'workflow_revision': 1, 'graph_sha256': graph_sha,
        'run_id': 'run', 'input_occurrence_id': 'b' * 64, 'source_sha256': doc['source_sha256'],
        'project_id': 'project', 'document_id': doc['document_id'], 'node_id': 'export', 'operation_id': ''}
    operation = ({'kind': kind, 'document': doc, 'output_root': '/output', 'recipe_sha256': P.RECIPE_SHA256}
                 if kind == 'freeze_export' else {'kind': kind, 'document': doc, 'plan': plan})
    identity['operation_id'] = hashlib.sha256(P.encoded([identity, operation])).hexdigest()
    return {'schema_version': 1, 'identity': identity, 'operation': operation}


def test_profile_has_no_lease_or_write_fields():
    request = {'cmd': 'workflow_owner', 'protocol': 1, 'action': 'profile', 'request_id': uid()}
    assert P.envelope(request) == request
    with pytest.raises(ValueError): P.envelope({**request, 'session_id': uid()})
    with pytest.raises(ValueError): P.envelope({**request, 'ack': True})
    events = []
    owner = H.WorkflowOwner(SimpleNamespace(), events.append)
    result = owner.handle(request)
    assert result['status'] == 'readback' and result['recipe_sha256'] == P.RECIPE_SHA256
    assert result['runtime_verified'] is False and owner.session is None


def test_graph_digest_is_rust_dto_order_not_input_dict_order():
    value, sha = graph()
    shuffled = {key: value[key] for key in reversed(value)}
    assert P.graph(shuffled, sha)[0] == value
    with pytest.raises(ValueError): P.graph(value, P.digest(value))
    with pytest.raises(ValueError): P.graph({**value, 'injected': True}, sha)


def test_exact_command_fingerprint_and_unknown_fields():
    value = command()
    assert P.command(value) == value
    changed = deepcopy(value); changed['operation']['output_root'] = '/other'
    with pytest.raises(ValueError): P.command(changed)
    changed = deepcopy(value); changed['operation']['ack'] = True
    with pytest.raises(ValueError): P.command(changed)
    changed = deepcopy(value); changed['identity']['document_id'] = None
    with pytest.raises(ValueError): P.command(changed)


def test_preset_graph_fails_before_ingestion_or_export(monkeypatch):
    owner = H.WorkflowOwner(SimpleNamespace(), lambda _: None)
    lease = {'binding': {'project_id': 'project', 'path': '/project.lrt'}, 'max_operations': 1}
    monkeypatch.setattr(owner, '_lease', lambda *a, **k: (None, lease))
    monkeypatch.setattr(owner, '_filesystem', lambda *a, **k: {'/output': ['1', '2']})
    value, sha = graph(preset=True)
    result = owner.handle({'cmd': 'workflow_owner', 'protocol': 1, 'action': 'preflight',
                          'request_id': uid(), 'session_id': uid(), 'graph': value, 'graph_sha256': sha})
    assert result['supported'] is False
    assert any(d['code'] == 'preset_owner_not_bound' for d in result['diagnostics'])
    assert owner.session is None and not owner.operations


def test_unknown_export_holds_ingestion_release_and_new_import():
    owner = H.WorkflowOwner(SimpleNamespace(), lambda _: None)
    owner.operations['a' * 64] = {'command': {'operation': {'kind': 'start_export'}},
                                  'receipt': {'result': {'status': 'unknown'}}}
    engine = SimpleNamespace(_workflow_owner_host=owner)
    for action in ('release', 'import', 'arm', 'cancel'):
        with pytest.raises(ValueError): H.guard_command(engine, 'ingest_session', {'action': action})
    H.guard_command(engine, 'workflow_owner', {'action': 'query'})
    H.guard_command(engine, 'workflow_owner', {'action': 'profile'})
    H.guard_command(engine, 'ingest_session', {'action': 'query'})


def test_same_operation_with_new_transport_id_cannot_start_again(monkeypatch):
    value = command()
    original = {'cmd': 'workflow_owner', 'protocol': 1, 'action': 'execute',
                'request_id': uid(), 'session_id': uid(), 'command': value}
    owner = H.WorkflowOwner(SimpleNamespace(), lambda _: None)
    record = {'request': original, 'command': value,
              'receipt': owner._receipt(value, {'status': 'unknown', 'reason': 'lost original dispatch'})}
    owner.requests[original['request_id']] = record
    owner.operations[value['identity']['operation_id']] = record
    def forbidden(*a, **k): raise AssertionError('must not redispatch or freeze')
    monkeypatch.setattr(owner, '_bound', forbidden)
    result = owner.handle({**original, 'request_id': uid()})
    assert result['receipt'] == record['receipt'] and result['status'] == 'unknown'


def test_missing_query_is_unknown_not_failure_or_retry(monkeypatch):
    owner = H.WorkflowOwner(SimpleNamespace(), lambda _: None)
    def forbidden(*a, **k): raise AssertionError('read cannot invoke mutation')
    monkeypatch.setattr(E, 'start', forbidden)
    result = owner.handle({'cmd': 'workflow_owner', 'protocol': 1, 'action': 'query',
        'request_id': uid(), 'session_id': uid(), 'original_request_id': uid(), 'operation_id': 'a' * 64})
    assert result['status'] == 'unknown' and 'receipt' not in result


def test_dispatch_without_receipt_is_unknown_not_success():
    engine = SimpleNamespace(_tasks={}, cmd_export=lambda command, **kwargs: None)
    frozen = {'command': {}, 'plan': {'plan_id': 'a' * 64}, 'destination_roots': {'/output': ['1', '2']}}
    result, task_id = E.start(engine, frozen, uid())
    assert result['status'] == 'unknown' and task_id is None


def test_exact_export_admission_error_is_definitive_no_start():
    def reject(command, *, trusted_result, trusted_destination_roots):
        trusted_result({'event': 'error', 'error': 'destination collision'})
    engine = SimpleNamespace(_tasks={}, cmd_export=reject)
    result, task_id = E.start(engine, {'command': {}, 'plan': {'plan_id': 'a' * 64}, 'destination_roots': {'/output': ['1', '2']}}, uid())
    assert result['status'] == 'failed' and task_id is None
    assert result['code'] == 'export_admission_rejected'


def test_open_review_cannot_mint_ack(monkeypatch):
    owner = H.WorkflowOwner(SimpleNamespace(), lambda _: None)
    monkeypatch.setattr(owner, '_lease', lambda _: (None, None))
    request = {'cmd': 'workflow_owner', 'protocol': 1, 'action': 'open_review',
               'request_id': uid(), 'session_id': uid(), 'operation_id': 'a' * 64, 'review_id': 'invented'}
    result = owner.handle(request)
    assert result['status'] == 'failed' and 'receipt' not in result
    with pytest.raises(ValueError): P.envelope({**request, 'review_ack': True})


def test_dispatch_rejection_never_overwrites_retained_pending():
    value = command()
    request = {'cmd': 'workflow_owner', 'protocol': 1, 'action': 'execute',
               'request_id': uid(), 'session_id': uid(), 'command': value}
    events = []
    owner = H.WorkflowOwner(SimpleNamespace(), events.append)
    record = {'request': request, 'command': value,
              'receipt': owner._receipt(value, {'status': 'pending', 'owner_receipt_id': 'real-task'})}
    owner.requests[request['request_id']] = record
    engine = SimpleNamespace(_workflow_owner_host=owner)
    result = H.dispatch_rejected(engine, request, 'later gate rejected transport replay', False, events.append)
    assert result['status'] == 'pending' and 'dispatch_rejected' not in result
    fresh = {**request, 'request_id': uid()}
    result = H.dispatch_rejected(engine, fresh, 'handler entry uncertain', True, events.append)
    assert result['status'] == 'unknown' and 'dispatch_rejected' not in result
    result = H.dispatch_rejected(engine, fresh, 'never entered handler', False, events.append)
    assert result['status'] == 'failed' and result['dispatch_rejected'] is True


def test_query_emits_original_terminal_before_readback(monkeypatch):
    events = []
    owner = H.WorkflowOwner(SimpleNamespace(), events.append)
    value = command()
    value['operation'] = {'kind': 'start_export', 'document': document(), 'plan': {}}
    request = {'cmd': 'workflow_owner', 'protocol': 1, 'action': 'execute',
               'request_id': uid(), 'session_id': uid(), 'command': value}
    record = {'request': request, 'command': value, 'dispatch_started': True,
              'task_id': 'original-task', 'frozen': {},
              'receipt': owner._receipt(value, {'status': 'pending', 'owner_receipt_id': 'original-task'})}
    owner.requests[request['request_id']] = record
    monkeypatch.setattr(owner, '_lease', lambda _: (None, None))
    monkeypatch.setattr(E, 'observe', lambda *a: {'status': 'failed', 'code': 'export_failed',
                                               'message': 'actual terminal no-output failure', 'retained_document': None})
    query = {'cmd': 'workflow_owner', 'protocol': 1, 'action': 'query',
             'request_id': uid(), 'session_id': request['session_id'],
             'original_request_id': request['request_id'], 'operation_id': value['identity']['operation_id']}
    owner.handle(query)
    assert len(events) == 2
    assert events[0]['request_id'] == request['request_id'] and events[0]['status'] == 'failed'
    assert events[1]['request_id'] == query['request_id'] and events[1]['status'] == 'readback'
    assert events[0]['receipt'] == events[1]['receipt']


def test_preflight_output_descriptor_pin_is_not_rebased(tmp_path, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'lumaretouch_engine.session', SimpleNamespace(IMAGE_EXTS={'.jpg'}))
    source, managed, output = (tmp_path / name for name in ('source', 'managed', 'output'))
    for path in (source, managed, output): path.mkdir()
    project = tmp_path / 'project.lrt'; project.write_bytes(b'{}')
    value, _ = graph()
    value['nodes'][0]['operation']['root'] = str(source)
    value['nodes'][1]['operation'].update(project_path=str(project), managed_root=str(managed))
    value['nodes'][-1]['operation']['output_root'] = str(output)
    pin = H.WorkflowOwner._filesystem(value['nodes'])
    assert pin == {str(output): [str(output.stat().st_dev), str(output.stat().st_ino)]}
    original = deepcopy(pin)
    output.rename(tmp_path / 'detached-output'); output.mkdir()
    with pytest.raises(ValueError, match='replaced'):
        H.WorkflowOwner._filesystem(value['nodes'], expected_destination_roots=pin)
    assert pin == original


def test_preview_and_start_pass_original_root_pin_without_mutation():
    pin = {'/output': ['123', '456']}
    calls = []
    def reject(command, *, trusted_result, trusted_destination_roots):
        calls.append(deepcopy(trusted_destination_roots))
        trusted_destination_roots['/output'][1] = '999'
        trusted_result({'event': 'error', 'error': 'real admission rejected'})
    engine = SimpleNamespace(_tasks={}, cmd_export=reject)
    with pytest.raises(ValueError): E.preview(engine, {'request_id': uid()}, pin)
    frozen = {'command': {}, 'plan': {'plan_id': 'a' * 64}, 'destination_roots': pin}
    result, task_id = E.start(engine, frozen, uid())
    assert result['status'] == 'failed' and task_id is None
    assert calls == [pin, pin] and pin == {'/output': ['123', '456']}


def test_import_skip_is_rejected_by_real_lease_capability(monkeypatch):
    owner = H.WorkflowOwner(SimpleNamespace(), lambda _: None)
    lease = {'binding': {'project_id': 'project', 'path': '/project.lrt'}, 'max_operations': 1}
    monkeypatch.setattr(owner, '_lease', lambda *a, **k: (None, lease))
    monkeypatch.setattr(owner, '_filesystem', lambda *a, **k: {'/output': ['1', '2']})
    value, _ = graph(); value['nodes'][1]['error_policy'] = 'skip'
    sha = hashlib.sha256(P.encoded(value)).hexdigest()
    result = owner.handle({'cmd': 'workflow_owner', 'protocol': 1, 'action': 'preflight',
        'request_id': uid(), 'session_id': uid(), 'graph': value, 'graph_sha256': sha})
    assert not result['supported'] and owner.session is None
    assert any(row['code'] == 'import_policy_requires_stop' for row in result['diagnostics'])


def test_bound_admission_failure_has_original_terminal_receipt(monkeypatch):
    owner = H.WorkflowOwner(SimpleNamespace(), lambda _: None)
    value = command()
    request = {'cmd': 'workflow_owner', 'protocol': 1, 'action': 'execute',
        'request_id': uid(), 'session_id': uid(), 'command': value}
    def reject(*args): raise ValueError('pinned output root was replaced')
    monkeypatch.setattr(owner, '_bound', reject)
    result = owner.handle(request)
    assert result['status'] == 'failed' and result['receipt']['result']['status'] == 'failed'
    assert result['receipt']['identity'] == value['identity']
    assert owner.requests[request['request_id']]['dispatch_started'] is False
    monkeypatch.setattr(owner, '_lease', lambda _: (None, None))
    query = {'cmd': 'workflow_owner', 'protocol': 1, 'action': 'query', 'request_id': uid(),
        'session_id': request['session_id'], 'original_request_id': request['request_id'],
        'operation_id': value['identity']['operation_id']}
    assert owner.handle(query)['receipt'] == result['receipt']


def test_terminal_negative_proof_checks_original_directory_source():
    # Static order specification, not runtime acceptance of filesystem races.
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / 'src/lumaretouch_engine/workflow_owner_export.py').read_text()
    observe = source[source.index('def observe('):]
    assert observe.index("verify_destination_roots(frozen['destination_roots'])") < observe.index("item = task['items'][0]")
    negative = observe[observe.index("if item.get('outputs')"):]
    assert "affirmative no-commit receipt" in negative
    assert "'code': 'export_failed'" not in negative
