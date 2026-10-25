"""AUTHORED / UNRUN host specifications with no actual imports or camera access."""
from copy import deepcopy
from types import SimpleNamespace
import threading
import uuid
import pytest
from lumaretouch_engine import ingest_session_host as H
from lumaretouch_engine import ingest_session_protocol as P


class Managed:
    def __init__(self):
        self.lock = threading.RLock()
        self.active = None
        self.uncertain = None
        self.requests = {}
        self.receipts = {}
        self.calls = []
        self.hook = None
        self.cancel = threading.Event()
        self.guard_error = None

    def adopt(self):
        pass

    def guard(self):
        if self.guard_error:
            raise ValueError(self.guard_error)

    def handle(self, payload, *, trusted_precommit=None, trusted_root=None):
        self.calls.append(deepcopy(payload))
        if payload['action'] == 'start':
            self.hook = trusted_precommit
            self.root_hook = trusted_root
            self.requests[payload['request_id']] = deepcopy(payload)
            self.active = payload['request_id']
            self.receipts[self.active] = {'event': 'managed_import_result', 'request_id': self.active,
                                          'status': 'pending'}
        elif payload['action'] == 'cancel':
            self.cancel.set()

    def close(self):
        self.cancel.set()


def fixture(monkeypatch):
    managed, events = Managed(), []
    engine = SimpleNamespace(_project={'project_id': 'project', 'docs': [], 'managed_import_receipts': {}},
        _project_path='/project.lrt', _project_disk_sha256='a' * 64, _project_dirty=False,
        _doc_index=-1, _load_id='loaded', _doc_path=None, _docs=[], _managed_import_controller=managed,
        _document_versions=lambda: SimpleNamespace(workspace='workspace'))
    monkeypatch.setattr(H, 'read_project', lambda path: (b'{}', engine._project_disk_sha256))
    owner = H.IngestSession(engine, events.append)
    arm = {'cmd': 'ingest_session', 'action': 'arm', 'request_id': str(uuid.uuid4()),
           'owner': 'workflow', 'max_operations': 2, 'expected': owner._binding()}
    return owner, engine, managed, events, arm


def test_saved_clean_guard_and_exact_binding_remain_mandatory(monkeypatch):
    owner, engine, managed, events, arm = fixture(monkeypatch)
    managed.guard_error = 'save first'
    assert owner.handle(arm)['status'] == 'failed'
    assert owner.lease is None
    managed.guard_error = None
    changed = deepcopy(arm); changed['expected']['workspace'] = 'another'
    assert owner.handle(changed)['status'] == 'failed'
    assert owner.lease is None and managed.calls == []


def test_lease_excludes_interactive_changes_and_raw_managed_starts(monkeypatch):
    owner, engine, managed, events, arm = fixture(monkeypatch)
    assert owner.handle(arm)['status'] == 'succeeded'
    for name, action in (('project', 'open'), ('project', 'save'), ('session', 'select'),
                         ('history', 'undo'), ('preset', 'apply'), ('export', 'start'),
                         ('managed_import', 'start'), ('_owned_tick', '')):
        assert owner.blocks(name, {'action': action})
    assert not owner.blocks('session', {'action': 'query'})
    assert not owner.blocks('project', {'action': 'state'})


def test_duplicate_arm_returns_original_and_conflict_does_not_replace_it(monkeypatch):
    owner, engine, managed, events, arm = fixture(monkeypatch)
    first = owner.handle(arm)
    assert owner.handle(arm) == first
    changed = {**arm, 'max_operations': 1}
    assert owner.handle(changed)['status'] == 'failed'
    assert owner.receipts[arm['request_id']] == first
    assert owner.handle(arm) == first


def install_pending(owner, managed):
    session = owner.lease['session_id']
    outer = str(uuid.uuid4())
    operation = P.operation_id(session, outer)
    request = {'cmd': 'ingest_session', 'action': 'import', 'request_id': outer, 'session_id': session,
               'paths': ['/incoming/a.jpg'], 'root': '/managed', 'root_identity': ['1', '2'], 'completed_sources': []}
    owner.requests[outer] = request
    owner.receipts[outer] = {'status': 'pending'}
    owner.operations[operation] = {'session_id': session, 'operation_id': operation,
        'request_id': outer, 'request': request, 'status': 'pending'}
    owner.lease['operation_id'] = operation
    managed.active = operation
    managed.receipts[operation] = {'request_id': operation, 'status': 'pending'}
    return session, outer, operation


def test_passthrough_is_exact_owned_query_or_cancel_only(monkeypatch):
    owner, engine, managed, events, arm = fixture(monkeypatch)
    owner.handle(arm)
    session, outer, operation = install_pending(owner, managed)
    query = {'cmd': 'ingest_session', 'action': 'query', 'request_id': str(uuid.uuid4()),
             'session_id': session, 'operation_id': operation}
    assert owner.managed_passthrough(query)
    assert not owner.managed_passthrough({**query, 'operation_id': str(uuid.uuid4())})
    assert not owner.managed_passthrough({**query, 'session_id': str(uuid.uuid4())})
    assert not owner.managed_passthrough({**query, 'extra': 'not authorized'})
    managed.uncertain = {'id': operation}
    assert owner.managed_passthrough(query)
    assert not owner.managed_passthrough({**query, 'action': 'cancel'})


def test_unknown_never_releases_and_query_never_reissues_start(monkeypatch):
    owner, engine, managed, events, arm = fixture(monkeypatch)
    owner.handle(arm)
    session, outer, operation = install_pending(owner, managed)
    managed.active = None
    managed.uncertain = {'id': operation}
    managed.receipts[operation] = {'request_id': operation, 'status': 'unknown'}
    query = {'cmd': 'ingest_session', 'action': 'query', 'request_id': str(uuid.uuid4()),
             'session_id': session, 'operation_id': operation}
    assert owner.handle(query)['operation']['status'] == 'unknown'
    release = {'cmd': 'ingest_session', 'action': 'release', 'request_id': str(uuid.uuid4()),
               'session_id': session}
    assert owner.handle(release)['status'] == 'unknown'
    assert owner.lease is not None
    assert all(call['action'] != 'start' for call in managed.calls)
    assert any(event['request_id'] == outer and event['action'] == 'import'
               and event['status'] == 'unknown' for event in events)


def test_original_outer_import_is_settled_only_after_verified_inner_terminal(monkeypatch):
    owner, engine, managed, events, arm = fixture(monkeypatch)
    owner.handle(arm)
    session, outer, operation = install_pending(owner, managed)
    managed.active = None
    managed.receipts[operation] = {'request_id': operation, 'status': 'succeeded', 'imported': 1}
    monkeypatch.setattr(owner, '_committed_documents', lambda op, lease: [{'document_id': 'actual-document'}])
    query = {'cmd': 'ingest_session', 'action': 'query', 'request_id': str(uuid.uuid4()),
             'session_id': session, 'operation_id': operation}
    result = owner.handle(query)
    assert result['status'] == 'readback' and result['operation']['status'] == 'succeeded'
    terminal = [event for event in events if event['request_id'] == outer]
    assert len(terminal) == 1 and terminal[0]['status'] == 'succeeded'
    assert terminal[0]['action'] == 'import'
    assert owner.lease['operation_id'] is None


def test_full_capacity_has_no_eviction_or_hidden_project_rotation(monkeypatch):
    owner, engine, managed, events, arm = fixture(monkeypatch)
    engine._project['managed_import_receipts'] = {str(uuid.uuid4()): {} for _ in range(255)}
    assert owner.handle(arm)['status'] == 'failed'
    assert owner.lease is None and len(engine._project['managed_import_receipts']) == 255
    assert managed.calls == []


def test_real_import_route_installs_exact_precommit_proof_not_a_json_flag(monkeypatch, tmp_path):
    import hashlib
    import os
    from lumaretouch_engine.source_relocation_io import signature
    owner, engine, managed, events, arm = fixture(monkeypatch)
    owner.handle(arm)
    source = tmp_path / 'chosen-name.CR3'
    source.write_bytes(b'opaque bytes, not a decoded or certified camera photograph')
    body = source.read_bytes()
    proof = {'path': str(source), 'sha256': hashlib.sha256(body).hexdigest(), 'size': len(body),
             'stat': [str(value) for value in signature(source.stat())],
             'occurrence_id': 'same-file-new-business-occurrence', 'completion': 'stable_read'}
    request = {'cmd': 'ingest_session', 'action': 'import', 'request_id': str(uuid.uuid4()),
               'session_id': owner.lease['session_id'], 'root': '/managed', 'root_identity': ['1', '2'],
               'paths': [str(source)], 'completed_sources': [proof]}
    accepted = owner.handle(request)
    assert accepted['status'] == 'pending'
    operation = accepted['operation']['operation_id']
    inner = managed.calls[0]
    assert inner['cmd'] == 'managed_import' and inner['mode'] == 'copy'
    assert 'trusted_precommit' not in inner and callable(managed.hook)
    target = '/managed/' + str(uuid.uuid5(uuid.UUID(operation), str(source))) + '.cr3'
    prepared = {'source': str(source), 'path': target, 'sha256': proof['sha256'], 'size': len(body),
                'signature': [int(value) for value in proof['stat']],
                'fingerprint': {'path': target, 'sha256': proof['sha256'], 'bytes': len(body), 'hash_level': 'full'}}
    managed.hook([prepared])
    changed = deepcopy(prepared); changed['sha256'] = 'b' * 64
    with pytest.raises(ValueError):
        managed.hook([changed])
    engine._project['name'] = 'changed project without a save'
    with pytest.raises(ValueError):
        managed.hook([prepared])
    assert owner.handle(request) == accepted
    assert len(managed.calls) == 1  # Exact repeat reads the original receipt only.


def test_malformed_identity_is_bounded_failed_result_not_exception(monkeypatch):
    owner, engine, managed, events, arm = fixture(monkeypatch)
    result = owner.handle({'cmd': 'ingest_session', 'action': 'state', 'request_id': []})
    assert result['status'] == 'failed' and result['request_id'] is None
    assert owner.lease is None and managed.calls == []


def test_more_than_256_completed_queries_keep_original_unknown_write(monkeypatch):
    owner, engine, managed, events, arm = fixture(monkeypatch)
    owner.handle(arm)
    session, outer, operation = install_pending(owner, managed)
    managed.active = None
    managed.uncertain = {'id': operation}
    managed.receipts[operation] = {'request_id': operation, 'status': 'unknown'}
    for _ in range(600):
        query = {'cmd': 'ingest_session', 'action': 'query', 'request_id': str(uuid.uuid4()),
                 'session_id': session, 'operation_id': operation}
        result = owner.handle(query)
        assert result['status'] == 'readback'
        assert result['operation']['status'] == 'unknown'
    assert owner.receipts[outer]['status'] == 'unknown'
    assert operation in owner.operations and owner.lease['operation_id'] == operation
    assert len(owner.requests) <= 3  # Arm, original import and latest completed read.
    assert all(call['action'] != 'start' for call in managed.calls)


def test_write_cap_keeps_query_cancel_release_capacity_and_never_prunes_uncertain_reads(monkeypatch):
    owner, engine, managed, events, arm = fixture(monkeypatch)
    owner.handle(arm)
    session = owner.lease['session_id']
    for index in range(P.MAX_RECEIPTS - P.RECOVERY_RESERVE - 1):
        request = {'cmd': 'ingest_session', 'action': 'import', 'request_id': str(uuid.uuid4())}
        owner._reserve(request)
        owner.receipts[request['request_id']] = {'status': 'succeeded'}
    assert len(owner.requests) == P.MAX_RECEIPTS - P.RECOVERY_RESERVE
    with pytest.raises(ValueError):
        owner._reserve({'cmd': 'ingest_session', 'action': 'import', 'request_id': str(uuid.uuid4())})
    retained_reads = []
    for status in ('unknown', 'failed'):
        request = {'cmd': 'ingest_session', 'action': 'query', 'request_id': str(uuid.uuid4()),
                   'session_id': session, 'operation_id': str(uuid.uuid4())}
        owner._reserve(request)
        owner.receipts[request['request_id']] = {'status': status}
        retained_reads.append(request['request_id'])
    for _ in range(300):
        result = owner.handle({'cmd': 'ingest_session', 'action': 'state', 'request_id': str(uuid.uuid4())})
        assert result['status'] == 'readback'
    assert all(rid in owner.requests and rid in owner.receipts for rid in retained_reads)
    cancel = {'cmd': 'ingest_session', 'action': 'cancel', 'request_id': str(uuid.uuid4()),
              'session_id': session, 'operation_id': str(uuid.uuid4())}
    owner._reserve(cancel)
    released = owner.handle({'cmd': 'ingest_session', 'action': 'release', 'request_id': str(uuid.uuid4()),
                             'session_id': session})
    assert released['status'] == 'succeeded' and owner.lease is None
    assert len(owner.requests) < P.MAX_RECEIPTS


def test_root_callback_rejects_replacement_before_destination_write(monkeypatch, tmp_path):
    import hashlib
    import os
    from lumaretouch_engine.source_relocation_io import signature
    owner, engine, managed, events, arm = fixture(monkeypatch)
    owner.handle(arm)
    source = tmp_path / 'source.jpg'
    source.write_bytes(b'authored opaque source fixture, not photographic evidence')
    root = tmp_path / 'managed'
    root.mkdir()
    pin = root.stat()
    proof = {'path': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
             'size': source.stat().st_size, 'stat': [str(v) for v in signature(source.stat())],
             'occurrence_id': 'directory-owner-fixture', 'completion': 'stable_read'}
    request = {'cmd': 'ingest_session', 'action': 'import', 'request_id': str(uuid.uuid4()),
               'session_id': owner.lease['session_id'], 'root': str(root),
               'root_identity': [str(pin.st_dev), str(pin.st_ino)],
               'paths': [str(source)], 'completed_sources': [proof]}
    assert owner.handle(request)['status'] == 'pending'
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        managed.root_hook(descriptor)
        root.rename(tmp_path / 'original-managed')
        root.mkdir()
        replacement = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with pytest.raises(ValueError):
                managed.root_hook(replacement)
            with pytest.raises(ValueError):
                managed.root_hook(descriptor)
        finally:
            os.close(replacement)
        assert list(root.iterdir()) == []
    finally:
        os.close(descriptor)
