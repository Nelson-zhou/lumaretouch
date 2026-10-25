"""Authored UNRUN destination ownership and legacy-neutral fixtures."""
import os
import pytest
from lumaretouch_engine import owned_export_destination as O
from lumaretouch_engine.export_destination_commit import commit_encoded_bytes, CommitFailure


def pin(path):
    value = path.stat()
    return [str(value.st_dev), str(value.st_ino)]


def test_owned_export_rejects_replacement_before_creating_output(tmp_path):
    root = tmp_path / 'output'
    root.mkdir()
    token = O.enter({str(root): pin(root)})
    try:
        root.rename(tmp_path / 'original-output')
        root.mkdir()
        with pytest.raises(CommitFailure) as error:
            commit_encoded_bytes(root / 'photo.jpg', b'opaque fixture, not JPEG acceptance')
        assert not error.value.committed
        assert list(root.iterdir()) == []
    finally:
        O.leave(token)


def test_exact_owned_parent_is_required_and_no_overwrite(tmp_path):
    token = O.enter({str(tmp_path): pin(tmp_path)})
    try:
        result = commit_encoded_bytes(tmp_path / 'out.bin', b'exact encoded bytes')
        assert result['committed']
        with pytest.raises(CommitFailure):
            commit_encoded_bytes(tmp_path / 'out.bin', b'never overwrite')
        assert (tmp_path / 'out.bin').read_bytes() == b'exact encoded bytes'
    finally:
        O.leave(token)


def test_none_context_keeps_generic_no_clobber_path(tmp_path):
    token = O.enter(None)
    try:
        assert commit_encoded_bytes(tmp_path / 'old-path.bin', b'unchanged writer')['committed']
    finally:
        O.leave(token)
