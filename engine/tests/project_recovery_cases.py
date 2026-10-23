"""UNRUN: focused local fixtures for Qoder. No execution evidence is claimed."""
from contextlib import nullcontext
import json
import threading

import pytest
from lumaretouch_engine import project as P
from lumaretouch_engine.project_recovery_store import RecoveryStore, RecoveryError
from lumaretouch_engine.project_recovery_scheduler import AutosaveScheduler


def store(tmp_path):
    return RecoveryStore(str(tmp_path / 'local-recovery'), reserve_bytes=0)


def publish(s, project=None):
    p = project or P.new_project('Recovery fixture')
    result = s.publish(json.dumps(p).encode(), {'revision': 1, 'native_receipts': []}, nullcontext)
    return p, result


def test_committed_candidate_roundtrip_and_nonoverwriting_restore(tmp_path):
    s = store(tmp_path)
    p, receipt = publish(s)
    assert s.list_candidates(p['project_id'])[0]['project_sha256'] == receipt['project_sha256']
    target = tmp_path / 'recovered-copy'
    result = s.restore_copy(receipt['candidate_id'], str(target), confirmed=True,
                            reviewed_sha256=receipt['project_sha256'])
    assert result['original_untouched']
    assert P.load(result['path'])['project_id'] != p['project_id']
    with pytest.raises(FileExistsError):
        s.restore_copy(receipt['candidate_id'], str(target), confirmed=True,
                       reviewed_sha256=receipt['project_sha256'])


def test_discard_is_recoverable_not_delete(tmp_path):
    s = store(tmp_path)
    p, receipt = publish(s)
    with pytest.raises(RecoveryError):
        s.discard(receipt['candidate_id'], confirmed=False)
    s.discard(receipt['candidate_id'], confirmed=True)
    assert s.list_candidates(p['project_id']) == []
    assert s.list_candidates(p['project_id'], area='trash')[0]['candidate_id'] == receipt['candidate_id']
    assert s.inspect(receipt['candidate_id'], area='trash')['receipt']['project_sha256'] == receipt['project_sha256']


def test_uncommitted_staging_is_not_offered_after_crash(tmp_path):
    s = store(tmp_path)
    stage = s.root / 'staging' / 'interrupted'
    stage.mkdir()
    (stage / 'partial.json').write_text('{')
    reopened = RecoveryStore(str(s.root), reserve_bytes=0)
    assert reopened.list_candidates() == []
    assert reopened.usage()['bytes'] >= 1


def test_tampered_candidate_is_reported_not_loaded(tmp_path):
    s = store(tmp_path)
    _, receipt = publish(s)
    path = s.root / 'candidates' / receipt['candidate_id'] / ('project' + P.SUFFIX)
    path.write_bytes(path.read_bytes() + b' ')
    assert s.list_candidates()[0]['phase'] == 'damaged'
    with pytest.raises(RecoveryError):
        s.inspect(receipt['candidate_id'])


def test_budget_never_evicts_saved_candidate(tmp_path):
    s = store(tmp_path)
    _, receipt = publish(s)
    s.budget_bytes = 1
    with pytest.raises(RecoveryError):
        publish(s)
    assert s.list_candidates()[0]['candidate_id'] == receipt['candidate_id']


def test_migration_backup_exact_and_source_unchanged(tmp_path):
    s = store(tmp_path)
    project = P.new_project('old')
    project['schema_version'] = P.COLOUR_EDITOR_SCHEMA
    raw = json.dumps(project).encode()
    source = tmp_path / 'old.json'
    source.write_bytes(raw)
    result = s.backup_before_migration(str(source))
    assert source.read_bytes() == raw
    assert result['project']['schema_version'] == P.SCHEMA
    from pathlib import Path
    assert Path(result['backup_path']).read_bytes() == raw


def test_new_schema_refuses_without_touching_original(tmp_path):
    s = store(tmp_path)
    p = P.new_project('future')
    p['schema_version'] = 'lrt.project.v999'
    source = tmp_path / 'future.json'
    raw = json.dumps(p).encode()
    source.write_bytes(raw)
    with pytest.raises(ValueError):
        s.backup_before_migration(str(source))
    assert source.read_bytes() == raw


def test_scheduler_unknown_native_receipt_and_lossy_asset_fence(tmp_path):
    scheduler = AutosaveScheduler(store(tmp_path))
    p = P.new_project('fenced')
    scheduler.switch(p['project_id'])
    proof = dict(project_id=p['project_id'], revision=1, original_path=None,
                 native_receipts=[{'request_id': 'unknown-write', 'phase': 'unknown'}], transaction_open=False)
    try:
        with pytest.raises(RecoveryError):
            scheduler.offer(p, **proof)
        proof['native_receipts'] = []
        p['dropped'] = [{'reason': 'unsupported accepted asset'}]
        with pytest.raises(RecoveryError):
            scheduler.offer(p, **proof)
    finally:
        assert scheduler.shutdown()['flushed'] is False


def test_switch_fences_inflight_publication(tmp_path):
    entered, release = threading.Event(), threading.Event()
    class PausingStore:
        def publish(self, raw, metadata, guard):
            entered.set()
            release.wait(5)
            with guard():
                raise AssertionError('Old project may not publish after switch')
    scheduler = AutosaveScheduler(PausingStore())
    p = P.new_project('old')
    scheduler.switch(p['project_id'])
    try:
        scheduler.offer(p, project_id=p['project_id'], revision=1, original_path=None,
                        native_receipts=[], transaction_open=False)
        assert entered.wait(5)
        scheduler.switch('new-project')
    finally:
        release.set()
        scheduler.shutdown()
    assert scheduler.status()['project_id'] == 'new-project'


def test_command_boundary_does_not_bless_partial_return_or_exception():
    from types import SimpleNamespace
    from lumaretouch_engine.project_recovery_runtime import begin, finish, observe
    runtime = SimpleNamespace(tainted=False, reason=None, revision=0)
    engine = SimpleNamespace(_project_recovery_runtime=runtime, EDIT_CMDS=('exposure',))
    boundary, wrapped = begin(engine, {'cmd':'exposure'}, lambda _: observe({'event':'error','error':'partial'}))
    wrapped({})
    finish(engine, boundary)
    assert runtime.tainted is True and runtime.revision == 0
    runtime.tainted = False
    boundary, wrapped = begin(engine, {'cmd':'exposure'}, lambda _: None)
    wrapped({})
    finish(engine, boundary)
    assert runtime.tainted is False and runtime.revision == 1


def test_rejected_admission_without_handler_does_not_taint():
    from types import SimpleNamespace
    from lumaretouch_engine.project_recovery_runtime import begin, finish
    runtime = SimpleNamespace(tainted=False, reason=None, revision=0)
    engine = SimpleNamespace(_project_recovery_runtime=runtime, EDIT_CMDS=('exposure',))
    boundary, _ = begin(engine, {'cmd':'exposure'}, lambda _: None)
    finish(engine, boundary, 'blocked before invocation')
    assert runtime.tainted is False and runtime.revision == 0


def test_interrupted_operation_journal_is_not_replayed(tmp_path):
    import uuid
    s = store(tmp_path)
    request = {'request_id':str(uuid.uuid4()),'project_id':'project', 'action':'restore','destination':'/uncreated-target'}
    s.operation_started(request)
    assert s.operations('project')[0]['phase'] == 'started'
    with pytest.raises(RecoveryError):
        s.operation_started(request)


def test_missing_asset_and_unknown_dataclass_are_rejected(tmp_path):
    s = store(tmp_path)
    p = P.new_project('asset fence')
    p['recovery_fixture'] = {'__asset__':'sha256:'+'a'*64}
    with pytest.raises(RecoveryError):
        publish(s, p)
    p['recovery_fixture'] = {'__dc__':'UnknownLiveObject','fields':{}}
    with pytest.raises(RecoveryError):
        publish(s, p)
