"""Descriptor-safe imports and no-clobber/durable preset installation."""
import errno
import os
from pathlib import Path
import pytest
from lumaretouch_engine import preset_store as P, scope as S


def doc():
    return {'schema': S.PRESET_SCHEMA, 'id': 'custom', 'name': '自定义', 'kind': 'custom',
            'modules': {S.OP_EXPOSURE: {'ev': 1.}}}


def test_concurrent_destination_is_never_overwritten(monkeypatch, tmp_path):
    real = os.link
    def race(source, target):
        Path(target).write_text('concurrent owner')
        return real(source, target)
    monkeypatch.setattr(P.os, 'link', race)
    with pytest.raises(S.ScopeError, match='未覆盖'): P.save(doc(), directory=str(tmp_path))
    assert (tmp_path/'custom.json').read_text() == 'concurrent owner'
    assert not list(tmp_path.glob('*.tmp'))


def test_unique_temp_does_not_follow_old_predictable_symlink(tmp_path):
    other = tmp_path/'keep'; other.write_text('preserve')
    (tmp_path/'custom.json.tmp').symlink_to(other)
    saved = P.save(doc(), directory=str(tmp_path))
    assert other.read_text() == 'preserve' and P.load_file(saved)['name'] == '自定义'
    assert (tmp_path/'custom.json.tmp').is_symlink()


def test_force_replace_and_parent_directory_fsync(monkeypatch, tmp_path):
    calls = []; real = os.fsync
    monkeypatch.setattr(P.os, 'fsync', lambda fd: (calls.append(fd), real(fd))[1])
    path = P.save(doc(), directory=str(tmp_path)); replacement = doc(); replacement['name'] = '新版'
    P.save(replacement, directory=str(tmp_path), force=True)
    assert P.load_file(path)['name'] == '新版' and len(calls) == 4


def test_temp_write_failure_is_definite_but_post_commit_sync_failure_is_unknown(monkeypatch, tmp_path):
    real = os.fsync; calls = []
    def fail_first(fd): raise OSError(errno.ENOSPC, 'no space')
    monkeypatch.setattr(P.os, 'fsync', fail_first)
    with pytest.raises(P.PresetStorageError) as caught: P.save(doc(), directory=str(tmp_path))
    assert not caught.value.outcome_unknown and not (tmp_path/'custom.json').exists()
    def fail_directory(fd):
        calls.append(fd)
        if len(calls) == 2: raise OSError(errno.EIO, 'directory sync failed')
        real(fd)
    monkeypatch.setattr(P.os, 'fsync', fail_directory)
    with pytest.raises(P.PresetStorageError) as caught: P.save(doc(), directory=str(tmp_path))
    assert caught.value.outcome_unknown and caught.value.committed
    assert P.load_file(str(tmp_path/'custom.json'))['id'] == 'custom'


def test_import_rejects_fifo_without_blocking(tmp_path):
    path = tmp_path/'pipe.json'; os.mkfifo(path)
    with pytest.raises(S.ScopeError, match='普通文件'): P.load_file(str(path))


def test_import_reads_pinned_descriptor_and_bounds_growth(monkeypatch, tmp_path):
    path = tmp_path/'growing.json'; path.write_bytes(b'x'*100)
    real = os.fstat
    def small(fd):
        info = real(fd)
        return type('Info', (), {'st_mode': info.st_mode, 'st_size': 1})()
    monkeypatch.setattr(P.os, 'fstat', small)
    with pytest.raises(S.ScopeError, match='实读 17'): P.load_file(str(path), max_bytes=16)


def test_uncertain_commit_syscall_has_null_commit_state(monkeypatch, tmp_path):
    def fail(*args): raise OSError(errno.EIO, 'commit result uncertain')
    monkeypatch.setattr(P.os, 'link', fail)
    with pytest.raises(P.PresetStorageError) as caught: P.save(doc(), directory=str(tmp_path))
    assert caught.value.outcome_unknown and caught.value.committed is None


def test_failed_force_replace_preserves_existing_file(monkeypatch, tmp_path):
    path = P.save(doc(), directory=str(tmp_path)); before = Path(path).read_bytes()
    def fail(*args): raise PermissionError(errno.EACCES, 'denied')
    monkeypatch.setattr(P.os, 'replace', fail)
    replacement = doc(); replacement['name'] = 'must not replace'
    with pytest.raises(P.PresetStorageError) as caught: P.save(replacement, directory=str(tmp_path), force=True)
    assert not caught.value.outcome_unknown and caught.value.committed is False
    assert Path(path).read_bytes() == before


def test_replacing_path_after_open_does_not_change_imported_descriptor(monkeypatch, tmp_path):
    path = tmp_path/'source.json'; path.write_text(S.dump_preset(doc()), encoding='utf-8')
    original = os.fstat; replaced = []
    def replace_path(fd):
        if not replaced:
            replaced.append(True); path.rename(tmp_path/'original.json')
            replacement = doc(); replacement['name'] = 'replacement'
            path.write_text(S.dump_preset(replacement), encoding='utf-8')
        return original(fd)
    monkeypatch.setattr(P.os, 'fstat', replace_path)
    assert P.load_file(str(path))['name'] == '自定义'
    assert P.load_file(str(path))['name'] == 'replacement'
