"""AUTHORED / UNRUN. Synthetic integrity fixtures; never real model acceptance."""
import hashlib
import io
import json
from pathlib import Path
import zipfile
import pytest
from lumaretouch_engine import lens_depth_setup as setup


def wheel(entries):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as archive:
        for name,data in entries.items():archive.writestr(name,data)
    return buffer.getvalue()


@pytest.mark.parametrize('name',['../escape.py','/absolute.py','pkg/../escape.py','bad.pth','pkg/cache.pyc','wheel.data/purelib/pkg.py'])
def test_optional_wheel_never_executes_unsupported_members(name):
    with pytest.raises(setup.ModelInstallError):list(setup._wheel_members(wheel({name:b'no execution'})))


def test_relative_model_root_rejected(monkeypatch):
    monkeypatch.setenv('XDG_DATA_HOME','relative')
    with pytest.raises(setup.ModelInstallError):setup.model_root()


def test_runtime_is_bound_to_retained_pinned_archive_not_mutable_receipt(tmp_path,monkeypatch):
    raw=wheel({'sample_depth/__init__.py':b'original source\n'})
    (tmp_path/'wheels').mkdir();(tmp_path/'wheels'/'fixture.whl').write_bytes(raw)
    lock={'wheels':[{'filename':'fixture.whl','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}]}
    monkeypatch.setattr(setup,'_lock',lambda:lock)
    monkeypatch.setattr(setup,'_base_identity',lambda:{'fixture':True})
    monkeypatch.setattr(setup,'_read',lambda p,n:Path(p).read_bytes())
    setup._runtime_inventory(tmp_path,extract=True)
    (tmp_path/'site-packages/sample_depth/__init__.py').write_bytes(b'changed source\n')
    (tmp_path/'receipt.json').write_text(json.dumps({'runtime_files':'forged'}))
    with pytest.raises(setup.ModelInstallError):setup.runtime_identity(tmp_path)


def test_missing_installed_runtime_cannot_claim_ready(tmp_path,monkeypatch):
    monkeypatch.setattr(setup,'_base_identity',lambda:{})
    monkeypatch.setattr(setup,'_lock',lambda:{})
    status=setup.model_status(tmp_path/'absent')
    assert status['ready'] is False and status['installed'] is False
    assert status['inference_acceptance']=='UNRUN'


def test_unresolved_license_evidence_blocks_setup_before_any_download(monkeypatch):
    lock={'profile':'cpython312-linux-x86_64-cpu-v1','closure_complete':True,
          'license_eligibility':'pending-primary-evidence','unresolved_license_evidence':['fixture-component']}
    monkeypatch.setattr(setup,'_read',lambda *_:json.dumps(lock).encode())
    with pytest.raises(setup.ModelInstallError,match='license evidence'):
        setup._lock()
