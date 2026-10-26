# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit author-hosted Swin2SR setup, AUTHORED/UNRUN.

No import/status download or base runtime installation. Pins and model license
come from the official immutable model revision, never user input or receipts.
RealESRGAN remains unsupported because its checkpoint license is unresolved.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys
import tempfile
import threading
import signal

from ..prompted_model_install import ModelInstallError, _lock_model, _run, _cancel

from .swin2sr_manifest import (MODEL_ID, MODEL_REVISION, CHECKPOINT_FILENAME,
    CHECKPOINT_SIZE_BYTES, CHECKPOINT_URL, CHECKPOINT_SHA256, MODEL_LICENSE)

EXTENSION = 'upscale-native-v1'
PROBE = 'swin2sr-classical-x2-native-cpu-v1'
CHECKPOINT_LICENSE = MODEL_LICENSE
MAX_SIDE = 1024
MAX_PIXELS = MAX_SIDE * MAX_SIDE
CORE_SIZE = MAX_SIDE  # Exactly one full-frame model window; no approximate border tiles.
HALO = 272  # Conservative graph support:36*7+10+ceil(1/2)=263, rounded above to8.
# Source-derived support, not measured numerical/photographic acceptance.
WALL_SECONDS = 610


def evidence_blockers():
    result = []
    if not isinstance(CHECKPOINT_SHA256, str) or re.fullmatch('[0-9a-f]{64}', CHECKPOINT_SHA256) is None:
        result.append('official_checkpoint_sha256_unestablished')
    if CHECKPOINT_LICENSE is None:
        result.append('checkpoint_specific_license_review_pending')
    return result


def _admit_evidence():
    blockers = evidence_blockers()
    if blockers:
        raise ModelInstallError('; '.join(blockers))


def root_path(root=None):
    base = Path(root) if root is not None else Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'lumaretouch'/'optional-models'/MODEL_ID/MODEL_REVISION
    if not base.is_absolute() or '..' in base.parts:
        raise ModelInstallError('Upscale root must be absolute without parent traversal')
    if any(path.is_symlink() for path in (base, *base.parents)):
        raise ModelInstallError('Upscale model path cannot traverse symlinks')
    return base


def _read(path, limit):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise ModelInstallError('Unsafe or oversized upscale artifact')
        data = stream.read(limit + 1)
        if len(data) != info.st_size or len(data) > limit:
            raise ModelInstallError('Upscale artifact changed during read')
        return data


def checkpoint_bytes(root=None):
    _admit_evidence()
    data = _read(root_path(root)/CHECKPOINT_FILENAME, CHECKPOINT_SIZE_BYTES)
    if len(data) != CHECKPOINT_SIZE_BYTES or hashlib.sha256(data).hexdigest() != CHECKPOINT_SHA256:
        raise ModelInstallError('Upscale checkpoint bytes differ from source-reviewed pin')
    return data


def base_identity():
    if sys.version_info[:2] != (3, 12) or platform.system() != 'Linux' or platform.machine() != 'x86_64' or sys.byteorder != 'little':
        raise ModelInstallError('First upscale profile requires CPython 3.12 Linux x86_64 little-endian')
    versions = {name: importlib.metadata.version(name) for name in ('torch', 'numpy')}
    if versions['torch'] != '2.7.1+cpu' or not versions['numpy'].startswith('2.'):
        raise ModelInstallError('Requires existing app torch 2.7.1+cpu and NumPy 2.x; setup does not replace base runtime')
    return versions


def runtime_identity(root=None):
    _admit_evidence()
    versions = base_identity()
    checkpoint_bytes(root)
    code = {name: hashlib.sha256(_read(Path(__file__).with_name(name), 1024*1024)).hexdigest()
            for name in ('setup.py', 'adapter.py', 'worker.py', '_network.py', '_stream.py', 'source.py', 'geometry.py', 'numeric.py', 'architecture.py', 'swin2sr_network.py', 'swin2sr_loader.py', 'swin2sr_manifest.py')}
    return {'model_id': MODEL_ID, 'checkpoint_sha256': CHECKPOINT_SHA256,
            'base_versions': versions, 'interpreter': str(Path(sys.executable).resolve()), 'code': code}


def model_status(root=None):
    status = {'extension_id': EXTENSION, 'model_id': MODEL_ID, 'installed': False, 'ready': False,
              'state': 'blocked', 'blockers': evidence_blockers(), 'output_mode': 'restore_native_dimensions',
              'max_pixels': MAX_PIXELS, 'max_side': MAX_SIDE, 'execution_mode': 'single_full_frame', 'acceptance': 'UNRUN', 'base_runtime_installation': False}
    if status['blockers']:
        status['reason'] = '; '.join(status['blockers'])
        return status
    try:
        identity = runtime_identity(root)
        status.update(installed=True, state='installed', reason='Explicit CPU readiness check required')
        proof = root_path(root)/'readiness.json'
        if proof.exists() and json.loads(_read(proof, 65536)) == {'probe': PROBE, 'runtime': identity}:
            status.update(ready=True, state='installed', reason='Bounded probe passed; photograph quality/performance remain unaccepted')
    except Exception as error:
        status.update(state='unsupported', reason=str(error)[:1024], blockers=[str(error)[:1024]])
    return status


def check_readiness(root=None, *, cancelled=None, progress=None, _owned=False):
    _admit_evidence()
    base = root_path(root)
    owner = None if _owned else _lock_model(base)
    try:
        identity = runtime_identity(base)
        (base/'readiness.json').unlink(missing_ok=True)
        if progress: progress({'extension_id': EXTENSION, 'phase': 'readiness', 'ready': False})
        with tempfile.TemporaryDirectory(prefix='.upscale-probe-', dir=base.parent) as directory:
            output = Path(directory)/'result.json'
            _run([sys.executable, '-B', '-m', 'lumaretouch_engine.upscale_v2.worker', '--root', str(base),
                  '--output', str(output), '--probe', '--parent-pid', str(os.getpid())],
                 cancelled, Path(directory)/'worker.log', timeout=WALL_SECONDS)
            expected = {'probe': PROBE, 'runtime': identity}
            if json.loads(_read(output, 65536)) != expected or runtime_identity(base) != identity:
                raise ModelInstallError('Upscale runtime changed or probe result mismatched')
            _cancel(cancelled)
            temporary = Path(directory)/'readiness.json'
            temporary.write_text(json.dumps(expected, sort_keys=True))
            os.replace(temporary, base/'readiness.json')
        return model_status(base)
    finally:
        if owner is not None: owner.close()


def install_model(root=None, *, cancelled=None, progress=None):
    # Fixed author-hosted safetensors only; no arbitrary URL, pip, or base replacement.
    _admit_evidence()
    from ..curated_extension_download import acquire
    from types import SimpleNamespace
    import shutil
    import time
    base_identity()
    base = root_path(root)
    owner = _lock_model(base)
    staging = None
    try:
        if shutil.disk_usage(base.parent).free < 1024**3:
            raise ModelInstallError('Upscale setup requires 1 GiB free staging space')
        staging = Path(tempfile.mkdtemp(prefix='.upscale-install-', dir=base.parent))
        profile = SimpleNamespace(CHECKPOINT_SHA256=CHECKPOINT_SHA256,
            CHECKPOINT_SIZE_BYTES=CHECKPOINT_SIZE_BYTES, CHECKPOINT_URL=CHECKPOINT_URL)
        def emit(phase, **values):
            if progress: progress({'extension_id': EXTENSION, 'model_id': MODEL_ID, 'phase': phase, **values})
        source = acquire(base, emit=emit, cancelled=lambda: _cancel(cancelled), profile=profile)
        shutil.copyfile(source, staging/CHECKPOINT_FILENAME)
        # Retain model/code Apache terms and provenance with the local artifact.
        for filename in ('swin2sr_LICENSE.txt', 'swin2sr_NOTICE.txt'):
            (staging/filename).write_bytes(_read(Path(__file__).with_name(filename), 65536))
        # Probe staged bytes before replacing any existing installation.
        check_readiness(staging, cancelled=cancelled, progress=progress, _owned=True)
        _cancel(cancelled)
        previous = None
        if base.exists():
            previous = base.parent/(base.name+'.retained-'+str(time.time_ns()))
            base.rename(previous)
        try:
            staging.rename(base)
        except Exception:
            if previous is not None and not base.exists(): previous.rename(base)
            raise
        staging = None
        result = model_status(base)
        emit('complete', **result)
        return result
    finally:
        if staging is not None: shutil.rmtree(staging, ignore_errors=True)
        owner.close()


def main():
    parser = argparse.ArgumentParser(description='Explicit AI clarity model setup; no source-photo access')
    choice = parser.add_mutually_exclusive_group(required=True)
    for action in ('status', 'install', 'check'): choice.add_argument('--'+action, action='store_true')
    args = parser.parse_args()
    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM): signal.signal(signum, lambda *_: stopped.set())
    emit = lambda value: print(json.dumps(value, ensure_ascii=False), flush=True)
    try:
        result = install_model(cancelled=stopped.is_set, progress=emit) if args.install else check_readiness(cancelled=stopped.is_set, progress=emit) if args.check else model_status()
        emit(result)
        return 0
    except Exception as error:
        emit({'extension_id': EXTENSION, 'model_id': MODEL_ID, 'state': 'error', 'ready': False, 'error': str(error)})
        return 2


if __name__ == '__main__': raise SystemExit(main())
