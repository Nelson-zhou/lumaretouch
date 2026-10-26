# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Fake transport and probe only; no quality acceptance.

Run only during the separately authorized local validation phase. These fixtures
must not download assets, import MediaPipe, install packages or infer photos.
"""
import hashlib
import io
import json
import pytest
from lumaretouch_engine import hand_shape_setup as S, hand_shape_manifest as M
from lumaretouch_engine import curated_extension_download as D


@pytest.fixture
def asset(tmp_path, monkeypatch):
    data=b'fixture hand asset, not a real model'
    digest=hashlib.sha256(data).hexdigest()
    for key,value in [('MODEL_SIZE_BYTES',len(data)),('CHECKPOINT_SIZE_BYTES',len(data)),
                      ('MODEL_SHA256',digest),('CHECKPOINT_SHA256',digest)]:
        monkeypatch.setattr(M,key,value)
    identity={'fixture':'selected-runtime'}
    monkeypatch.setattr(S,'_identity',lambda:identity)
    return tmp_path/'hand',data,identity


def fake_probe(monkeypatch, identity):
    def run(command,*args,**kwargs):
        from pathlib import Path
        output=Path(command[command.index('--output')+1])
        output.write_text(json.dumps({'probe':S.PROBE,'runtime':identity}))
    monkeypatch.setattr(S,'_run',run)


def test_fixed_hand_url_rejects_redirects_and_foreign_profiles():
    D.checked_url(M.MODEL_URL,M)
    for url in ['http://storage.googleapis.com/mediapipe-models/x',
                M.MODEL_URL+'?replacement=1','https://huggingface.co/model',
                'https://storage.googleapis.com/mediapipe-models/other.task']:
        with pytest.raises(ValueError): D.checked_url(url,M)
    with pytest.raises(ValueError): D.checked_url(M.MODEL_URL)


def test_status_offline_requires_probe_and_current_runtime(asset,monkeypatch):
    base,data,identity=asset; base.mkdir(); (base/M.MODEL_FILENAME).write_bytes(data)
    monkeypatch.setattr(D.urllib.request,'build_opener',lambda *a:pytest.fail('status must not network'))
    assert S.model_status(base)['installed'] and not S.model_status(base)['ready']
    (base/'readiness.json').write_text(json.dumps({'probe':S.PROBE,'runtime':identity}))
    assert S.model_status(base)['ready']
    monkeypatch.setattr(S,'_identity',lambda:{'fixture':'changed-runtime'})
    assert S.model_status(base)['readiness']=='stale'
    assert not S.model_status(base)['ready']


def test_runtime_absence_prevents_network(asset,monkeypatch):
    base,_,_=asset
    def absent(): raise S.ModelInstallError('Missing reviewed MediaPipe')
    monkeypatch.setattr(S,'_identity',absent)
    monkeypatch.setattr(D,'acquire',lambda *a,**k:pytest.fail('must not download before runtime admission'))
    assert S.model_status(base)['state']=='unsupported'
    with pytest.raises(S.ModelInstallError,match='Missing'): S.install_model(base)


def test_verified_partial_install_and_recheck_are_offline(asset,monkeypatch):
    base,data,identity=asset
    D.partial_path(base,M).write_bytes(data)
    monkeypatch.setattr(D.urllib.request,'build_opener',lambda *a:pytest.fail('complete verified partial is offline'))
    fake_probe(monkeypatch,identity)
    assert S.install_model(base)['ready']
    assert (base/M.MODEL_FILENAME).read_bytes()==data
    assert S.check_readiness(base)['ready']


def test_failed_candidate_does_not_publish(asset,monkeypatch):
    base,data,_=asset; D.partial_path(base,M).write_bytes(data)
    def fail(*args,**kwargs): raise S.ModelInstallError('probe failed')
    monkeypatch.setattr(S,'_run',fail)
    with pytest.raises(S.ModelInstallError,match='probe failed'): S.install_model(base)
    assert not base.exists()
    assert D.partial_path(base,M).read_bytes()==data


def test_cancellation_retains_partial_without_publishing(asset):
    base,data,_=asset; D.partial_path(base,M).write_bytes(data[:5])
    with pytest.raises(S.InstallCancelled): S.install_model(base,cancelled=lambda:True)
    assert not base.exists()
    assert D.partial_path(base,M).read_bytes()==data[:5]


def test_changed_installed_bytes_are_unavailable(asset,monkeypatch):
    base,data,identity=asset; base.mkdir(); (base/M.MODEL_FILENAME).write_bytes(data)
    (base/'readiness.json').write_text(json.dumps({'probe':S.PROBE,'runtime':identity}))
    (base/M.MODEL_FILENAME).write_bytes(b'x'*len(data))
    assert S.model_status(base)['state']=='invalid'
    assert not S.model_status(base)['ready']


def test_symlink_destination_rejected(asset,tmp_path):
    base,_,_=asset; target=tmp_path/'other'; target.mkdir(); base.symlink_to(target)
    with pytest.raises(S.ModelInstallError,match='symlink'): S.install_model(base)
    assert list(target.iterdir())==[]


def test_hand_range_resume_uses_fixed_url_and_full_hash(asset,monkeypatch):
    base,data,_=asset; D.partial_path(base,M).write_bytes(data[:5]); calls=[]
    class Response(io.BytesIO):
        status=206
        headers={'Content-Range':f'bytes 5-{len(data)-1}/{len(data)}','Content-Length':str(len(data)-5)}
    class Opener:
        def open(self,request,timeout):
            calls.append(request); return Response(data[5:])
    monkeypatch.setattr(D.urllib.request,'build_opener',lambda *args:Opener())
    assert D.acquire(base,profile=M,emit=lambda *a,**k:None,cancelled=lambda:None).read_bytes()==data
    assert calls[0].full_url==M.MODEL_URL and calls[0].get_header('Range')=='bytes=5-'
