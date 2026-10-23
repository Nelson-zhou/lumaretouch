"""AUTHORED / UNRUN: source relocation acceptance cases, no image/model fixtures."""
import copy
import hashlib
import json
import os
import pytest
from lumaretouch_engine import source_relocation_transaction as T
from lumaretouch_engine.source_relocation_io import Budget, hash_file


def fixture(tmp_path, content=b'original content with stable metadata'):
    old = str(tmp_path / 'missing.jpg')
    candidate = tmp_path / 'renamed.bin'
    candidate.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    row = {'path': old, 'fingerprint': {'path': old, 'sha256': sha, 'bytes': len(content), 'hash_level': 'full'},
           'versions': [{'id': 'named-version', 'recipe': {'face': {'asset_sha256': sha}, 'body': {'source_path': old}}}],
           'active_version': 'named-version', 'canonical_id': 'persisted-if-already-present'}
    project = {'project_id': 'project', 'docs': [row], 'assets': {'support': 'unchanged'}, 'history': ['unchanged']}
    identities = [{'document_id': 'runtime-id', 'revision': 7, 'old_path': old}]
    plan = T.preview(project, identities, [str(candidate)], None, lambda: False)
    return project, identities, candidate, plan


def test_renamed_exact_bytes_preserve_everything_except_paths(tmp_path):
    project, _, candidate, plan = fixture(tmp_path)
    before = copy.deepcopy(project)
    result, updates = T.stage(project, plan, {'runtime-id': str(candidate)}, lambda: False)
    expected = copy.deepcopy(project)
    expected['docs'][0]['path'] = str(candidate)
    expected['docs'][0]['fingerprint']['path'] = str(candidate)
    assert result == expected
    assert project == before
    assert len(updates) == 1


def test_same_size_changed_bytes_not_a_candidate(tmp_path):
    project, ids, candidate, _ = fixture(tmp_path)
    candidate.write_bytes(b'x' * candidate.stat().st_size)
    result = T.preview(project, ids, [str(candidate)], None, lambda: False)
    assert result['rows'][0]['candidates'] == []
    assert result['errors']


def test_head_only_is_not_exact_original(tmp_path):
    project, ids, candidate, _ = fixture(tmp_path)
    project['docs'][0]['fingerprint']['hash_level'] = 'head'
    with pytest.raises(ValueError, match='完整 SHA-256'):
        T.preview(project, ids, [str(candidate)], None, lambda: False)


def test_duplicate_candidates_require_explicit_choice(tmp_path):
    project, ids, candidate, _ = fixture(tmp_path)
    duplicate = tmp_path / 'copy.jpg'
    duplicate.write_bytes(candidate.read_bytes())
    plan = T.preview(project, ids, [str(candidate), str(duplicate)], None, lambda: False)
    assert len(plan['rows'][0]['candidates']) == 2
    with pytest.raises(ValueError): T.stage(project, plan, {}, lambda: False)
    result, _ = T.stage(project, plan, {'runtime-id': str(duplicate)}, lambda: False)
    assert result['docs'][0]['path'] == str(duplicate)


def test_candidate_mutation_after_preview_refuses_commit(tmp_path):
    project, _, candidate, plan = fixture(tmp_path)
    candidate.write_bytes(b'x' * candidate.stat().st_size)
    with pytest.raises(ValueError): T.stage(project, plan, {'runtime-id': str(candidate)}, lambda: False)


def test_replaced_inode_same_content_requires_new_preview(tmp_path):
    project, _, candidate, plan = fixture(tmp_path)
    replacement = tmp_path / 'replacement'
    replacement.write_bytes(candidate.read_bytes())
    os.replace(replacement, candidate)
    with pytest.raises(ValueError): T.stage(project, plan, {'runtime-id': str(candidate)}, lambda: False)


def test_cancel_is_not_partial_preview(tmp_path):
    project, ids, candidate, _ = fixture(tmp_path)
    with pytest.raises(InterruptedError): T.preview(project, ids, [str(candidate)], None, lambda: True)


def test_symlink_and_symlink_ancestor_rejected(tmp_path):
    _, _, candidate, _ = fixture(tmp_path)
    link = tmp_path / 'link'
    link.symlink_to(candidate)
    with pytest.raises(OSError): hash_file(str(link), Budget(lambda: False))
    folder = tmp_path / 'folder-link'
    folder.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError): hash_file(str(folder / candidate.name), Budget(lambda: False))


def test_stale_project_does_not_apply(tmp_path):
    project, _, candidate, plan = fixture(tmp_path)
    project['history'].append('new edit')
    with pytest.raises(ValueError): T.stage(project, plan, {'runtime-id': str(candidate)}, lambda: False)


def test_existing_other_document_path_not_merged(tmp_path):
    project, ids, candidate, _ = fixture(tmp_path)
    project['docs'].append({'path': str(candidate), 'fingerprint': {}, 'versions': []})
    plan = T.preview(project, ids, [str(candidate)], None, lambda: False)
    with pytest.raises(ValueError, match='另一文档'):
        T.stage(project, plan, {'runtime-id': str(candidate)}, lambda: False)


def test_atomic_success_and_disk_compare_swap(tmp_path):
    project, _, candidate, plan = fixture(tmp_path)
    path = tmp_path / 'project.json'
    path.write_bytes(T.encoded(project))
    old_sha = T.read_project(str(path))[1]
    output, _ = T.stage(project, plan, {'runtime-id': str(candidate)}, lambda: False)
    receipt = T.persist(str(path), output, old_sha, 'operation', lambda p: None, lambda: False, lambda: None)
    assert receipt['status'] == 'succeeded'
    stored = json.loads(path.read_bytes())
    assert stored['docs'][0]['path'] == str(candidate)
    assert stored['assets'] == project['assets']
    with pytest.raises(ValueError):
        T.persist(str(path), project, old_sha, 'stale', lambda p: None, lambda: False, lambda: None)


def test_failure_before_replace_keeps_old_project(tmp_path, monkeypatch):
    project, _, _, _ = fixture(tmp_path)
    path = tmp_path / 'project.json'
    raw = T.encoded(project)
    path.write_bytes(raw)
    def fail(*args, **kwargs): raise OSError('injected replace failure')
    monkeypatch.setattr(T.os, 'replace', fail)
    with pytest.raises(OSError):
        T.persist(str(path), project, hashlib.sha256(raw).hexdigest(), 'op', lambda p: None, lambda: False, lambda: None)
    assert path.read_bytes() == raw
    assert not list(tmp_path.glob('.lrt-relocation-*'))


def test_directory_fsync_failure_is_unknown_not_rollback(tmp_path, monkeypatch):
    project, _, _, _ = fixture(tmp_path)
    path = tmp_path / 'project.json'
    raw = T.encoded(project)
    path.write_bytes(raw)
    original, calls = T.os.fsync, []
    def fail_second(fd):
        calls.append(fd)
        if len(calls) == 2: raise OSError('injected directory durability failure')
        return original(fd)
    monkeypatch.setattr(T.os, 'fsync', fail_second)
    receipt = T.persist(str(path), project, hashlib.sha256(raw).hexdigest(), 'op', lambda p: None, lambda: False, lambda: None)
    assert receipt['status'] == 'unknown'
    assert json.loads(path.read_bytes())['source_relocation_receipt']['operation_id'] == 'op'


def test_history_alias_requires_original_full_content(tmp_path):
    from lumaretouch_engine.source_relocation_history import matches
    project, _, candidate, _ = fixture(tmp_path)
    row = copy.deepcopy(project['docs'][0])
    old = row['path']
    row['path'] = str(candidate)
    assert not matches(row, old)
    row['_source_relocation_aliases'] = {old: row['fingerprint']['sha256']}
    assert matches(row, old)
    candidate.write_bytes(b'x' * candidate.stat().st_size)
    assert not matches(row, old)
