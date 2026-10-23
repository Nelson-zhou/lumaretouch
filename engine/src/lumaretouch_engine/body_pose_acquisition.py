"""Optional asset adapter. Import/status/inference are offline, like SAM's port.

Only an explicit installer call can acquire bytes. Expected checksum provenance
is community-published, not locally verified. Runtime package installation
is not performed here and must reuse the application's reviewed packaging path.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import urllib.request
from . import body_pose_manifest as M
from .prompted_model_install import ModelInstallError, _verified_file, _cancel


def model_root(root=None):
    return Path(root) if root is not None else Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))) / 'lumaretouch/optional-models' / M.MODEL_ID


def require_pin():
    if type(M.MODEL_SHA256) is not str or len(M.MODEL_SHA256) != 64 or any(c not in '0123456789abcdef' for c in M.MODEL_SHA256) or type(M.MODEL_SIZE_BYTES) is not int or not 0 < M.MODEL_SIZE_BYTES <= 64*1024*1024:
        raise ModelInstallError('Body pose acquisition is pending a reviewed exact SHA-256 and byte size; a versioned URL alone is not a strong pin')


def verified_model_bytes(root=None):
    require_pin()
    base = model_root(root)
    receipt_path=base/'receipt.json'
    if receipt_path.is_symlink() or receipt_path.stat().st_size>16384:raise ModelInstallError('Invalid body pose receipt file')
    with receipt_path.open('rb') as handle:receipt_bytes=handle.read(16385)
    if len(receipt_bytes)>16384:raise ModelInstallError('Body pose receipt exceeds budget')
    receipt = json.loads(receipt_bytes)
    expected = {'version': 1, 'model_id': M.MODEL_ID, 'url': M.MODEL_URL, 'sha256': M.MODEL_SHA256, 'bytes': M.MODEL_SIZE_BYTES, 'license': M.MODEL_LICENSE}
    if receipt != expected or (base/M.MODEL_FILENAME).is_symlink():
        raise ModelInstallError('Body pose receipt does not match the reviewed asset')
    return _verified_file(base/M.MODEL_FILENAME, M.MODEL_SIZE_BYTES, M.MODEL_SHA256)


def status(root=None):
    out = {'model_id': M.MODEL_ID, 'installed': False, 'state': 'pin-pending', 'license': M.MODEL_LICENSE, 'model_sha256': M.MODEL_SHA256, 'download_bytes': M.MODEL_SIZE_BYTES, 'limitations': list(M.LIMITATIONS), 'pin_status': M.PIN_STATUS, 'pin_sources': list(M.PIN_SOURCES)}
    try:
        require_pin()
        out['state'] = 'not-installed'
        if model_root(root).exists():
            verified_model_bytes(root)
            out.update(installed=True, state='verified-bytes-runtime-unvalidated')
    except (OSError, ValueError, ModelInstallError) as error:
        out['reason'] = str(error)
        if M.MODEL_SHA256 is not None: out['state'] = 'invalid'
    return out


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ModelInstallError('Body pose asset redirected away from the reviewed URL')


def install_model(*, root=None, cancelled=None, progress=None):
    """Native optional-acquisition process only; never call from engine startup.

    Reuses bounded verification/cancellation semantics of prompted_model_install.
    Has no photograph argument. No pip/compile/network occurs before pin review.
    """
    require_pin(); _cancel(cancelled)
    base = model_root(root)
    if base.exists():
        verified_model_bytes(root)
        return status(root)
    base.parent.mkdir(parents=True, exist_ok=True)
    lock = base.parent/(base.name+'.install-lock')
    lock.mkdir()  # Existing lock is an explicit refusal, not automatic deletion.
    staging = None
    try:
        staging = Path(tempfile.mkdtemp(prefix='.body-pose-', dir=base.parent))
        count = 0; digest = hashlib.sha256(); started = time.monotonic()
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(M.MODEL_URL, timeout=30) as response, (staging/M.MODEL_FILENAME).open('xb') as output:
            if response.headers.get('Content-Length') not in (None, str(M.MODEL_SIZE_BYTES)):
                raise ModelInstallError('Body pose response length changed')
            while True:
                _cancel(cancelled)
                if time.monotonic()-started>600:raise ModelInstallError('Body pose acquisition timed out without publishing a partial asset')
                chunk = response.read(min(65536, M.MODEL_SIZE_BYTES-count+1))
                if not chunk: break
                count += len(chunk)
                if count > M.MODEL_SIZE_BYTES: raise ModelInstallError('Body pose asset exceeds reviewed byte budget')
                output.write(chunk); digest.update(chunk)
                if progress: progress({'model_id': M.MODEL_ID, 'phase': 'model', 'downloaded_bytes': count, 'total_bytes': M.MODEL_SIZE_BYTES})
            output.flush(); os.fsync(output.fileno())
        if count != M.MODEL_SIZE_BYTES or digest.hexdigest() != M.MODEL_SHA256:
            raise ModelInstallError('Body pose downloaded bytes failed SHA-256/size verification')
        notices=Path(__file__).resolve().parent/'body_pose_licenses'
        for name in ('APACHE-2.0.txt','NOTICE.txt'):
            shutil.copyfile(notices/name,staging/name)
        receipt = {'version': 1, 'model_id': M.MODEL_ID, 'url': M.MODEL_URL, 'sha256': M.MODEL_SHA256, 'bytes': M.MODEL_SIZE_BYTES, 'license': M.MODEL_LICENSE}
        (staging/'receipt.json').write_text(json.dumps(receipt,sort_keys=True),encoding='utf-8')
        _cancel(cancelled)
        if base.exists(): raise ModelInstallError('Body pose destination appeared during installation')
        staging.rename(base); staging = None
        return status(root)
    finally:
        if staging is not None: shutil.rmtree(staging, ignore_errors=True)
        lock.rmdir()


def main():
    """Dedicated optional installer CLI; no engine or image arguments accepted."""
    import argparse
    import signal
    import threading
    parser=argparse.ArgumentParser(description='Explicit verified optional body-pose asset acquisition')
    parser.add_argument('--install',action='store_true')
    parser.add_argument('--root',type=Path)
    args=parser.parse_args()
    cancelled=threading.Event()
    signal.signal(signal.SIGTERM,lambda _signal,_frame:cancelled.set())
    def emit(value):print(json.dumps(value,sort_keys=True),flush=True)
    try:
        result=install_model(root=args.root,cancelled=cancelled.is_set,progress=emit) if args.install else status(args.root)
        emit({'event':'body_pose_model_status',**result})
        return 0
    except (OSError,ValueError,ModelInstallError) as error:
        emit({'event':'body_pose_model_status','model_id':M.MODEL_ID,'installed':False,'state':'cancelled' if cancelled.is_set() else 'failed','reason':str(error)})
        return 1


if __name__=='__main__':
    raise SystemExit(main())
