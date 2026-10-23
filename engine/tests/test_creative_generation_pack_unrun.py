"""Authored source-only fixtures. UNRUN: no imports/tests executed during authoring."""
from pathlib import Path
import hashlib
import sys

import pytest

from lumaretouch_engine import creative_generation_manifest as manifest
from lumaretouch_engine import creative_generation_pack as pack


def test_unresolved_upstream_metadata_cannot_be_owner_approved(tmp_path):
    (tmp_path / "manifest.json").write_text('{"verified": true}')
    result = pack.status(tmp_path)
    assert result["available"] is False
    assert result["code"] == "upstream_manifest_incomplete"
    assert result["downloadsAttempted"] is False


def test_status_does_not_import_model_modules(tmp_path):
    before = set(sys.modules)
    pack.status(tmp_path)
    assert not ({"torch", "diffusers", "transformers", "safetensors"} & (set(sys.modules) - before))


def test_absolute_local_root_required():
    with pytest.raises(pack.PackUnavailable, match="absolute local"):
        pack.verify_pack("remote/repository")
    with pytest.raises(pack.PackUnavailable, match="absolute local"):
        pack.verify_pack("/tmp/../model")


def test_reviewed_manifest_has_no_pickle_or_code_entries():
    assert len(manifest.FILES) == 19
    assert len({pin.path for pin in manifest.FILES}) == 19
    assert all(Path(pin.path).suffix in {".json", ".txt", ".safetensors"} for pin in manifest.FILES)
    assert len([pin for pin in manifest.FILES if pin.sha256]) == 5
    assert manifest.UPSTREAM_REVISION_MEMBERSHIP_VERIFIED is False


def _fixture_contract(monkeypatch):
    data = b"fixture only, not a production model"
    pin = manifest.FilePin("prior/fixture.json", hashlib.sha256(data).hexdigest(), len(data), "fixture")
    monkeypatch.setattr(manifest, "FILES", (pin,))
    monkeypatch.setattr(manifest, "UPSTREAM_REVISION_MEMBERSHIP_VERIFIED", True)
    monkeypatch.setattr(manifest, "RUNTIME_VERSIONS", {"diffusers": "0.29.0"})
    monkeypatch.setattr(pack.metadata, "version", lambda _: "0.29.0")
    return data


def test_completed_model_pins_cannot_admit_unverified_runtime(tmp_path, monkeypatch):
    _fixture_contract(monkeypatch)
    assert pack.status(tmp_path)["code"] == "runtime_provenance_unverified"


def test_exact_local_bytes_and_extras_rejected(tmp_path, monkeypatch):
    # Isolate byte/version checks without claiming production code admission.
    monkeypatch.setattr(pack, "_verify_runtime_provenance", lambda: None)
    data = _fixture_contract(monkeypatch)
    (tmp_path / "prior").mkdir()
    (tmp_path / "prior/fixture.json").write_bytes(data)
    first = pack.verify_pack(tmp_path)
    assert len(first.identity) == 64
    (tmp_path / "injected.py").write_text("raise RuntimeError('must never import')")
    assert pack.status(tmp_path)["available"] is False


def test_changed_bytes_and_symlink_refused(tmp_path, monkeypatch):
    # Isolate byte/version checks without claiming production code admission.
    monkeypatch.setattr(pack, "_verify_runtime_provenance", lambda: None)
    data = _fixture_contract(monkeypatch)
    (tmp_path / "prior").mkdir()
    leaf = tmp_path / "prior/fixture.json"
    leaf.write_bytes(data[::-1])
    assert pack.status(tmp_path)["code"] == "pack_file_hash"
    leaf.unlink()
    outside = tmp_path.parent / (tmp_path.name + "-external.json")
    outside.write_bytes(data)
    leaf.symlink_to(outside)
    assert pack.status(tmp_path)["code"] == "unsafe_pack_entry"


def test_runtime_versions_are_not_compatibility_ranges(tmp_path, monkeypatch):
    # Isolate byte/version checks without claiming production code admission.
    monkeypatch.setattr(pack, "_verify_runtime_provenance", lambda: None)
    _fixture_contract(monkeypatch)
    monkeypatch.setattr(pack.metadata, "version", lambda _: "0.29.1")
    assert pack.status(tmp_path)["code"] == "runtime_version"


def test_read_access_time_is_not_content_mutation(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(pack, '_verify_runtime_provenance', lambda: None)
    data = _fixture_contract(monkeypatch)
    (tmp_path / 'prior').mkdir()
    (tmp_path / 'prior/fixture.json').write_bytes(data)
    actual_fstat = pack.os.fstat
    calls = []
    def advancing_atime(fd):
        info = actual_fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        values = {name: getattr(info, name) for name in fields}
        values['st_atime'] = info.st_atime + len(calls)
        calls.append(fd)
        return SimpleNamespace(**values)
    monkeypatch.setattr(pack.os, 'fstat', advancing_atime)
    assert len(pack.verify_pack(tmp_path).identity) == 64
    assert len(calls) == 2
