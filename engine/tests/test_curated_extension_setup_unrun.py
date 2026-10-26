"""AUTHORED / UNRUN. Protocol fixtures only; never evidence of install or AI quality.

Do not execute under the current source-only authorization. Network and model
operation are faked. Real first installation/device/portrait checks remain open.
"""
import hashlib
import io
from pathlib import Path
import pytest
from lumaretouch_engine import curated_extension_download as D
from lumaretouch_engine import prompted_model_install as I


class Response(io.BytesIO):
    def __init__(self, data, code=200, headers=None):
        super().__init__(data)
        self.status = code
        self.headers = headers or {'Content-Length':str(len(data))}


@pytest.fixture
def checkpoint(monkeypatch, tmp_path):
    data = b'reviewed checkpoint bytes'
    monkeypatch.setattr(D.M,'CHECKPOINT_SIZE_BYTES',len(data))
    monkeypatch.setattr(D.M,'CHECKPOINT_SHA256',hashlib.sha256(data).hexdigest())
    return tmp_path/'version', data


def opener(monkeypatch, response, calls):
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            return response
    monkeypatch.setattr(D.urllib.request,'build_opener',lambda *args:Opener())


def test_resume_exact_content_range(checkpoint, monkeypatch):
    base, data = checkpoint
    D.partial_path(base).write_bytes(data[:7]); calls=[]; events=[]
    opener(monkeypatch,Response(data[7:],206,{'Content-Range':f'bytes 7-{len(data)-1}/{len(data)}',
                                          'Content-Length':str(len(data)-7)}),calls)
    path=D.acquire(base,emit=lambda phase,**v:events.append((phase,v)),cancelled=lambda:None)
    assert calls[0].get_header('Range')=='bytes=7-'
    assert path.read_bytes()==data and events[-1][0]=='verifying'


def test_range_ignored_restarts_instead_of_appends(checkpoint, monkeypatch):
    base,data=checkpoint
    D.partial_path(base).write_bytes(data[:7]);calls=[]
    opener(monkeypatch,Response(data),calls)
    assert D.acquire(base,emit=lambda *a,**k:None,cancelled=lambda:None).read_bytes()==data


def test_bad_range_refuses_before_append(checkpoint, monkeypatch):
    base,data=checkpoint
    D.partial_path(base).write_bytes(data[:7]);calls=[]
    opener(monkeypatch,Response(data[7:],206,{'Content-Range':f'bytes 0-{len(data)-1}/{len(data)}'}),calls)
    with pytest.raises(ValueError,match='range'):
        D.acquire(base,emit=lambda *a,**k:None,cancelled=lambda:None)
    assert D.partial_path(base).read_bytes()==data[:7]


def test_full_hash_failure_resets_untrusted_partial(checkpoint, monkeypatch):
    base,data=checkpoint;calls=[]
    opener(monkeypatch,Response(b'x'*len(data)),calls)
    with pytest.raises(ValueError,match='SHA256'):
        D.acquire(base,emit=lambda *a,**k:None,cancelled=lambda:None)
    assert D.partial_path(base).read_bytes()==b''


def test_complete_verified_partial_is_offline(checkpoint, monkeypatch):
    base,data=checkpoint
    D.partial_path(base).write_bytes(data)
    monkeypatch.setattr(D.urllib.request,'build_opener',lambda *a:pytest.fail('must not open network'))
    assert D.acquire(base,emit=lambda *a,**k:None,cancelled=lambda:None).read_bytes()==data


def test_partial_symlink_never_written(checkpoint, tmp_path):
    base,data=checkpoint
    victim=tmp_path/'photo';victim.write_bytes(b'unchanged')
    D.partial_path(base).symlink_to(victim)
    with pytest.raises(ValueError,match='Unsafe'):
        D.acquire(base,emit=lambda *a,**k:None,cancelled=lambda:None)
    assert victim.read_bytes()==b'unchanged'


def test_existing_install_without_probe_is_not_ready(tmp_path, monkeypatch):
    root=tmp_path/'installed';root.mkdir()
    monkeypatch.setattr(I,'_base_identity',lambda:{'runtime':'base'})
    monkeypatch.setattr(I,'installed_runtime_identity',lambda **k:{'runtime_sha256':'actual'})
    monkeypatch.setattr(I,'verified_checkpoint_bytes',lambda **k:b'verified')
    status=I.model_status(root=root)
    assert status['installed'] and status['checkpoint_verified']
    assert status['ready'] is False and status['readiness']=='unchecked'


def test_failed_recheck_does_not_keep_passing_receipt(tmp_path, monkeypatch):
    root=tmp_path/'installed';root.mkdir();(root/'readiness.json').write_text('{}')
    monkeypatch.setattr(I,'_base_identity',lambda:{'runtime':'base'})
    monkeypatch.setattr(I,'installed_runtime_identity',lambda **k:{'runtime_sha256':'actual'})
    monkeypatch.setattr(I,'verified_checkpoint_bytes',lambda **k:b'verified')
    def fail(*a,**k):raise I.ModelInstallError('bounded probe failed')
    monkeypatch.setattr(I,'_run',fail)
    with pytest.raises(I.ModelInstallError,match='probe failed'):
        I.check_readiness(root=root,_owner_held=True)
    assert not (root/'readiness.json').exists()
