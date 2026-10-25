"""Authored, NOT executed: workflow save and private dispatch boundary fixtures.

The deterministic prepared-manifest double isolates transaction mechanics. It
does not validate the full project codec, pixels, UI, native journal, process
crashes or real storage durability. Those acceptance stages remain UNRUN.
"""
import ast
from copy import deepcopy
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from lumaretouch_engine import creative_document_storage as CS
from lumaretouch_engine import project as PJ
from lumaretouch_engine import project_recovery_runtime as R
from lumaretouch_engine import workflow_preset_dispatch as D
from lumaretouch_engine import workflow_preset_save as S


@pytest.fixture
def saved(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    root.mkdir()
    path = root / 'work.lrproject.json'
    before = b'{"previous":"exact saved bytes"}\n'
    path.write_bytes(before)
    chunk = b'new immutable creative bytes\x00\xff'
    key = 'sha256:' + sha256(chunk).hexdigest()
    body = {'updated_ns': 123456789, 'assets': {
        key: {'kind': 'bytes', 'shape': None, 'dtype': None,
              'bytes': len(chunk), 'blob': key}},
        'payload': {CS.MARKER: 1, 'bytes': len(chunk), 'sha256': key, 'chunks': [key]}}
    data = json.dumps(body, ensure_ascii=False, sort_keys=True).encode('utf-8')
    supplied = {'target-only': 'scoped project owned by caller'}
    preparation = []

    def prepare(project):
        assert project is supplied
        preparation.append(project)
        return deepcopy(body), data, {key: chunk}

    monkeypatch.setattr(PJ, '_prepare_save', prepare)
    monkeypatch.setattr(CS.shutil, 'disk_usage', lambda _: SimpleNamespace(free=10**12))
    checks = []
    return SimpleNamespace(root=root, path=path, before=before, before_sha=sha256(before).hexdigest(),
        body=body, data=data, key=key, chunk=chunk, supplied=supplied, preparation=preparation,
        checks=checks, recheck=lambda: checks.append('owner'))


def persist(f, recheck=None):
    return S.persist(f.supplied, str(f.path), f.before_sha, recheck or f.recheck)


def assert_no_staging(root):
    assert not list(root.glob('.lrt-workflow-preset-*'))
    assert not list(root.glob('.lrt-creative-stage-*'))


def test_exact_save_uses_prepared_codec_bytes_and_no_fabricated_receipt(saved):
    f = saved
    result = persist(f)
    assert result == {'status': 'succeeded', 'sha256': sha256(f.data).hexdigest(),
        'bytes': len(f.data), 'updated_ns': f.body['updated_ns'], 'project': f.body}
    assert f.path.read_bytes() == f.data
    assert CS.read_blobs(f.body, f.path) == {f.key: f.chunk}
    assert len(f.preparation) == 1 and len(f.checks) == 2
    assert f.supplied == {'target-only': 'scoped project owned by caller'}
    assert 'source_relocation_receipt' not in result['project']
    assert 'managed_import_receipt' not in result['project']
    assert_no_staging(f.root)


def test_missing_owner_check_refuses_before_prepare_or_filesystem(saved):
    f = saved
    with pytest.raises(ValueError, match='retained owner'):
        S.persist(f.supplied, str(f.path), f.before_sha, None)
    assert not f.preparation and f.path.read_bytes() == f.before
    assert set(f.root.iterdir()) == {f.path}


def test_codec_failure_precedes_any_write(saved, monkeypatch):
    f = saved
    def reject(_):
        raise ValueError('invalid complete project')
    monkeypatch.setattr(PJ, '_prepare_save', reject)
    with pytest.raises(ValueError, match='invalid complete'):
        persist(f)
    assert set(f.root.iterdir()) == {f.path}


def test_initial_cas_is_exact_bytes_not_semantic_json(saved):
    f = saved
    changed = b'{ "previous" : "exact saved bytes" }'
    assert json.loads(changed) == json.loads(f.before)
    f.path.write_bytes(changed)
    with pytest.raises(ValueError, match='changed'):
        persist(f)
    assert f.path.read_bytes() == changed
    assert not f.checks and not CS.sidecar_path(f.path).exists()


def test_final_cas_preserves_a_newer_writer_and_retains_orphan_blob(saved):
    f = saved
    changed = b'newer external project bytes'
    def recheck():
        f.checks.append('owner')
        if len(f.checks) == 2:
            f.path.write_bytes(changed)
    with pytest.raises(ValueError, match='CAS changed'):
        persist(f, recheck)
    assert f.path.read_bytes() == changed
    assert (CS.sidecar_path(f.path) / f.key[7:]).read_bytes() == f.chunk
    assert_no_staging(f.root)


def test_final_owner_rejection_never_rolls_back_or_replaces_old_manifest(saved):
    f = saved
    def recheck():
        f.checks.append('owner')
        if len(f.checks) == 2:
            raise ValueError('retained target changed')
    with pytest.raises(ValueError, match='retained target changed'):
        persist(f, recheck)
    assert f.path.read_bytes() == f.before
    assert (CS.sidecar_path(f.path) / f.key[7:]).read_bytes() == f.chunk
    assert_no_staging(f.root)


def test_existing_sidecar_generations_are_not_deleted_or_rewritten(saved):
    f = saved
    root = CS.sidecar_path(f.path)
    root.mkdir()
    old = b'old inactive history, retained forever by this writer'
    old_path = root / sha256(old).hexdigest()
    old_path.write_bytes(old)
    existing = root / f.key[7:]
    existing.write_bytes(f.chunk)
    identities = {path: (path.stat().st_ino, path.stat().st_mtime_ns) for path in (old_path, existing)}
    persist(f)
    assert old_path.read_bytes() == old and existing.read_bytes() == f.chunk
    assert identities == {path: (path.stat().st_ino, path.stat().st_mtime_ns) for path in identities}


def test_corrupt_existing_hash_named_blob_is_not_overwritten(saved):
    f = saved
    root = CS.sidecar_path(f.path)
    root.mkdir()
    corrupt = root / f.key[7:]
    corrupt.write_bytes(b'x' * len(f.chunk))
    with pytest.raises(ValueError, match='hash/length'):
        persist(f)
    assert corrupt.read_bytes() == b'x' * len(f.chunk)
    assert f.path.read_bytes() == f.before


def test_cooperating_writer_lock_is_nonblocking(saved):
    f = saved
    with open(str(f.path) + '.relocation.lock', 'a+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            persist(f)
    assert f.path.read_bytes() == f.before and not f.checks


@pytest.mark.parametrize('leaf', ['manifest', 'lock'])
def test_symlink_leaf_is_not_followed(saved, leaf):
    f = saved
    external = f.root.parent / 'outside'
    external.write_bytes(f.before)
    target = f.path if leaf == 'manifest' else Path(str(f.path) + '.relocation.lock')
    if target.exists():
        target.unlink()
    target.symlink_to(external)
    with pytest.raises((OSError, ValueError)):
        persist(f)
    assert target.is_symlink() and external.read_bytes() == f.before


def test_symlink_ancestor_is_rejected(saved):
    f = saved
    alias = f.root.parent / 'alias'
    alias.symlink_to(f.root, target_is_directory=True)
    with pytest.raises((OSError, ValueError)):
        S.persist(f.supplied, str(alias / f.path.name), f.before_sha, f.recheck)
    assert f.path.read_bytes() == f.before


def test_fifo_manifest_is_rejected_without_waiting_for_a_writer(saved):
    f = saved
    f.path.unlink()
    os.mkfifo(f.path)
    with pytest.raises(ValueError, match='regular'):
        persist(f)
    assert stat.S_ISFIFO(f.path.stat().st_mode)


def test_parent_substitution_during_final_check_cannot_cas_another_directory(saved, monkeypatch):
    """Regression: CAS must read A, never validate B and then replace pinned A."""
    f = saved
    moved = f.root.parent / 'retained-original-directory'
    newer = b'newer target in retained original directory'
    real_open = os.open
    armed, substituted = [False], [False]

    def recheck():
        f.checks.append('owner')
        if len(f.checks) == 2:
            armed[0] = True

    def replacing_open(path, flags, mode=0o777, *, dir_fd=None):
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        if armed[0] and not substituted[0] and path == f.root.name and flags & os.O_DIRECTORY:
            substituted[0] = True
            # The just-opened check FD still points to A, so its fstat alone
            # matches. A fresh pathname walk now sees B's original-byte decoy.
            f.path.write_bytes(newer)
            f.root.rename(moved)
            f.root.mkdir()
            f.path.write_bytes(f.before)
        return fd

    monkeypatch.setattr(os, 'open', replacing_open)
    with pytest.raises(ValueError, match='CAS changed|directory was replaced'):
        persist(f, recheck)
    assert substituted[0]
    assert (moved / f.path.name).read_bytes() == newer
    assert f.path.read_bytes() == f.before
    assert_no_staging(moved)


def test_directory_substitution_during_blob_write_refuses_manifest_commit(saved, monkeypatch):
    f = saved
    moved = f.root.parent / 'original-directory'
    real_write = CS.write_blobs
    def write_then_substitute(*args, **kwargs):
        result = real_write(*args, **kwargs)
        f.root.rename(moved)
        f.root.mkdir()
        f.path.write_bytes(f.before)
        return result
    monkeypatch.setattr(CS, 'write_blobs', write_then_substitute)
    with pytest.raises(ValueError, match='directory was replaced'):
        persist(f)
    assert f.path.read_bytes() == f.before
    assert (moved / f.path.name).read_bytes() == f.before
    assert_no_staging(moved)


def test_pinned_read_refuses_oversize_without_reading_body(saved, monkeypatch):
    f = saved
    monkeypatch.setattr(S, 'MAX_PROJECT', len(f.before) - 1)
    def forbidden(*_):
        raise AssertionError('Oversize body must not be read')
    monkeypatch.setattr(os, 'read', forbidden)
    with pytest.raises(ValueError, match='bounded'):
        persist(f)


def test_pinned_read_detects_leaf_replacement_during_read(saved, monkeypatch):
    f = saved
    real_read = os.read
    replaced = [False]
    def racing_read(fd, count):
        raw = real_read(fd, count)
        if not replaced[0] and raw:
            replaced[0] = True
            replacement = f.root / 'external-stage'
            replacement.write_bytes(f.before)
            os.replace(replacement, f.path)
        return raw
    monkeypatch.setattr(os, 'read', racing_read)
    with pytest.raises(ValueError, match='pinned read'):
        persist(f)
    assert f.path.read_bytes() == f.before and not f.checks


@pytest.mark.parametrize('replace_first', [False, True])
def test_any_replace_attempt_error_is_unknown_and_never_retried(saved, monkeypatch, replace_first):
    f = saved
    real_replace = os.replace
    attempts = []
    def uncertain(*args, **kwargs):
        attempts.append((args, kwargs))
        if replace_first:
            real_replace(*args, **kwargs)
        raise OSError('injected replacement outcome unavailable')
    monkeypatch.setattr(os, 'replace', uncertain)
    result = persist(f)
    assert result['status'] == 'unknown' and result['requires_readback'] is True
    assert result['expected_sha256'] == sha256(f.data).hexdigest()
    assert len(attempts) == 1
    assert f.path.read_bytes() == (f.data if replace_first else f.before)
    assert_no_staging(f.root)


def test_directory_sync_error_after_replacement_is_unknown(saved, monkeypatch):
    f = saved
    real_replace, real_fsync = os.replace, os.fsync
    replaced = [False]
    def replace(*args, **kwargs):
        real_replace(*args, **kwargs)
        replaced[0] = True
    def fsync(fd):
        if replaced[0] and stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError('injected directory sync failure')
        real_fsync(fd)
    monkeypatch.setattr(os, 'replace', replace)
    monkeypatch.setattr(os, 'fsync', fsync)
    result = persist(f)
    assert result['status'] == 'unknown' and result['requires_readback'] is True
    assert f.path.read_bytes() == f.data


def test_post_replace_readback_mismatch_is_unknown_without_rollback(saved, monkeypatch):
    f = saved
    real_replace = os.replace
    newer = b'external replacement after the save commit point'
    def replace(*args, **kwargs):
        real_replace(*args, **kwargs)
        f.path.write_bytes(newer)
    monkeypatch.setattr(os, 'replace', replace)
    result = persist(f)
    assert result['status'] == 'unknown' and result['requires_readback'] is True
    assert f.path.read_bytes() == newer


def test_descriptor_cleanup_error_after_commit_cannot_escape_as_retryable(saved, monkeypatch):
    f = saved
    real_open, real_close = os.open, os.close
    lock_fd, closed = [None], []
    def opening(path, flags, mode=0o777, *, dir_fd=None):
        fd = real_open(path, flags, mode, dir_fd=dir_fd)
        if path == f.path.name + '.relocation.lock':
            lock_fd[0] = fd
        return fd
    def closing(fd):
        real_close(fd)
        if fd == lock_fd[0]:
            closed.append(fd)
            raise OSError('injected uncertain descriptor close')
    monkeypatch.setattr(os, 'open', opening)
    monkeypatch.setattr(os, 'close', closing)
    result = persist(f)
    assert result['status'] == 'unknown' and result['requires_readback'] is True
    assert closed == [lock_fd[0]]  # No retry of a possibly reused descriptor.
    assert f.path.read_bytes() == f.data


def test_post_replace_parent_substitution_is_unknown_not_success(saved, monkeypatch):
    f = saved
    moved = f.root.parent / 'committed-original-directory'
    real_replace = os.replace
    def replace(*args, **kwargs):
        real_replace(*args, **kwargs)
        f.root.rename(moved)
        f.root.mkdir()
        f.path.write_bytes(f.before)
    monkeypatch.setattr(os, 'replace', replace)
    result = persist(f)
    assert result['status'] == 'unknown' and result['requires_readback'] is True
    assert (moved / f.path.name).read_bytes() == f.data
    assert f.path.read_bytes() == f.before


def test_pre_replace_file_sync_failure_preserves_manifest(saved, monkeypatch):
    f = saved
    real_sync = os.fsync
    def fsync(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError('injected precommit file sync failure')
        real_sync(fd)
    monkeypatch.setattr(os, 'fsync', fsync)
    with pytest.raises(OSError, match='precommit file sync'):
        persist(f)
    assert f.path.read_bytes() == f.before
    assert_no_staging(f.root)


class DispatchProbe:
    """Routing double, not a substitute for real server/history acceptance."""
    def __init__(self, body):
        self.body, self.calls, self.table = body, [], {'sentinel': object()}

    def _dispatch_table(self):
        self.calls.append('table')
        return self.table

    def _process_line(self, line, table):
        assert table is self.table
        payload = json.loads(line)
        self.calls.append(payload)
        self.body(self, payload)


def test_dispatch_admission_is_exact_engine_and_payload_and_does_not_escape(monkeypatch):
    original = {'message': {'cmd': 'workflow_owner'}, 'failed': False}
    monkeypatch.setattr(R._local, 'boundary', original, raising=False)
    request = {'cmd': 'preset', 'action': 'apply', 'id': 'color-warm', 'document_id': 'load-1', 'request_id': 'request-1'}
    def body(engine, payload):
        assert D.permits(engine, 'preset', payload)
        assert not D.permits(object(), 'preset', payload)
        assert not D.permits(engine, 'load_image', payload)
        assert not D.permits(engine, 'preset', {**payload, 'id': 'another'})
        assert not D.permits(engine, 'preset', {**payload, '_workflow_handoff': True})
        # A real nested dispatcher owns and finishes a separate recovery boundary.
        R._local.boundary = {'message': payload, 'failed': False}
        R._local.boundary = None
    engine = DispatchProbe(body)
    checks = []
    D.dispatch(engine, request, lambda: checks.append('check'))
    assert checks == ['check'] and engine.calls == ['table', request]
    assert R._local.boundary is original
    assert not D.permits(engine, 'preset', request)


def test_nested_handoff_is_refused_without_recheck_or_second_dispatch(monkeypatch):
    original = {'message': {'cmd': 'workflow_owner'}}
    monkeypatch.setattr(R._local, 'boundary', original, raising=False)
    request = {'cmd': 'load_image', 'path': '/exact/image.png', 'document_id': 'stable-id'}
    def body(engine, payload):
        def forbidden():
            raise AssertionError('Nested handoff must fail before owner recheck')
        with pytest.raises(ValueError, match='Nested'):
            D.dispatch(engine, payload, forbidden)
        assert D.permits(engine, 'load_image', payload)
    engine = DispatchProbe(body)
    D.dispatch(engine, request, lambda: None)
    assert len(engine.calls) == 2 and R._local.boundary is original
    assert not D.permits(engine, 'load_image', request)


def test_dispatch_exception_restores_outer_recovery_and_closes_admission(monkeypatch):
    original = {'message': {'cmd': 'workflow_owner'}, 'failed': True}
    monkeypatch.setattr(R._local, 'boundary', original, raising=False)
    request = {'cmd': 'preset', 'action': 'apply'}
    def fail(engine, payload):
        R._local.boundary = {'message': payload, 'failed': True}
        raise RuntimeError('original dispatcher failed')
    engine = DispatchProbe(fail)
    with pytest.raises(RuntimeError, match='original dispatcher'):
        D.dispatch(engine, request, lambda: None)
    assert R._local.boundary is original and original['failed'] is True
    assert not D.permits(engine, 'preset', request)


def test_dispatch_owner_rejection_never_enters_normal_command_lane():
    engine = DispatchProbe(lambda *_: pytest.fail('Handler must not run'))
    def reject():
        raise ValueError('old retained target')
    with pytest.raises(ValueError, match='old retained target'):
        D.dispatch(engine, {'cmd': 'preset', 'action': 'apply'}, reject)
    assert engine.calls == []


@pytest.mark.parametrize('payload', [
    {'cmd': 'export', '_workflow_handoff': True},
    {'cmd': 'project', 'action': 'save'},
])
def test_unrelated_commands_cannot_borrow_private_admission(payload):
    engine = DispatchProbe(lambda *_: pytest.fail('Handler must not run'))
    assert not D.permits(engine, payload['cmd'], payload)
    with pytest.raises(ValueError, match='unrelated'):
        D.dispatch(engine, payload, lambda: None)
    assert not engine.calls


def test_nonfinite_payload_cannot_leak_private_scope(monkeypatch):
    original = {'message': {'cmd': 'workflow_owner'}}
    monkeypatch.setattr(R._local, 'boundary', original, raising=False)
    engine = DispatchProbe(lambda *_: pytest.fail('Handler must not run'))
    request = {'cmd': 'preset', 'amount': float('nan')}
    with pytest.raises(ValueError):
        D.dispatch(engine, request, lambda: None)
    assert not engine.calls and R._local.boundary is original
    assert not D.permits(engine, 'preset', request)


def test_static_normal_dispatcher_retains_history_and_post_history_preset_finish():
    """Source contract only; no importing/instantiating the full image engine."""
    source = Path(S.__file__).with_name('server.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    process = next(node for node in ast.walk(tree)
                   if isinstance(node, ast.FunctionDef) and node.name == '_process_line')
    calls = [node for node in ast.walk(process) if isinstance(node, ast.Call)]
    attributes = {node.func.attr for node in calls if isinstance(node.func, ast.Attribute)}
    assert {'guard_command', '_history_capture', '_history_record', '_preset_controller'} <= attributes
    records = [node.lineno for node in calls if isinstance(node.func, ast.Attribute)
               and node.func.attr == '_history_record']
    finishes = [node.lineno for node in calls if isinstance(node.func, ast.Attribute)
        and node.func.attr == 'finish' and isinstance(node.func.value, ast.Call)
        and isinstance(node.func.value.func, ast.Attribute)
        and node.func.value.func.attr == '_preset_controller']
    assert records and finishes and max(records) < min(finishes)
