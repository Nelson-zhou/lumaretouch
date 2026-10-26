# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit hand asset setup using the shared native/download/process owners.

AUTHORED / UNRUN. No dependency installation, photo input or import-time IO.
Only --install accesses the one fixed official asset. Status is offline; check
executes a bounded generated-image CPU capability probe, not photo acceptance.
"""
import argparse
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import threading
from . import hand_shape_manifest as M
from .prompted_model_install import ModelInstallError, InstallCancelled, _lock_model, _run, _cancel

PROBE = 'hand-landmarker-cpu-image-buffer-v1'


def _base(root=None):
    from .hand_shape_model import model_root
    base = model_root(root)
    if not base.is_absolute() or '..' in base.parts or any(p.is_symlink() for p in (base, *base.parents)):
        raise ModelInstallError('Hand model path must be absolute and contain no symlinks or parent traversal')
    return base


def _identity():
    if sys.platform != 'linux' or sys.version_info < (3, 10):
        raise ModelInstallError('Hand setup requires selected Linux Python 3.10+; no base runtime auto-install')
    from .hand_shape_model import _read_regular
    packages = {}
    for name in ('mediapipe', 'numpy'):
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise ModelInstallError('Selected runtime lacks '+name+'; prepare the reviewed app runtime explicitly, not global pip') from error
        if name == 'mediapipe' and dist.version != M.RUNTIME_VERSION:
            raise ModelInstallError('Selected MediaPipe must be '+M.RUNTIME_VERSION+'; no dependency replacement')
        packages[name] = {'version':dist.version, 'location':str(dist.locate_file('')),
                          'record_sha256':sha256((dist.read_text('RECORD') or '').encode()).hexdigest()}
        if name == 'mediapipe':
            source = Path(dist.locate_file('mediapipe/tasks/python/vision/hand_landmarker.py'))
            packages[name]['producer_path'] = str(source.absolute())
            packages[name]['producer_sha256'] = sha256(_read_regular(source,2*1024*1024)).hexdigest()
    executable = Path(sys.executable).resolve()
    info = executable.stat()
    return {'python':str(executable), 'version':sys.version,
            'executable_stamp':[info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns],
            'packages':packages, 'model_sha256':M.MODEL_SHA256}


def verify_producer_origin(path, identity=None):
    """Bind the loaded Python producer to the selected distribution's source."""
    from .hand_shape_model import _read_regular
    expected = (identity or _identity())['packages']['mediapipe']
    if (str(Path(path).absolute()) != expected['producer_path'] or
            sha256(_read_regular(path,2*1024*1024)).hexdigest() != expected['producer_sha256']):
        raise ModelInstallError('Loaded hand producer differs from selected reviewed runtime')


def model_status(root=None):
    from .hand_shape_model import verified_model_bytes, _read_regular
    from .curated_extension_download import partial_size
    result = {'extension_id':M.EXTENSION_ID,'model_id':M.MODEL_ID,'state':'not-installed',
        'installed':False,'ready':False,'readiness':'unchecked','checkpoint_verified':False,
        'download_bytes':M.MODEL_SIZE_BYTES,'license':M.MODEL_LICENSE,
        'automatic_base_runtime_setup':False,'inference_acceptance':'UNRUN',
        'readiness_scope':'generated blank CPU image capability only, not detection accuracy or photo quality'}
    try:
        base = _base(root)
        result['resume_bytes'] = partial_size(base, M)
        identity = _identity()
    except (OSError, ValueError, ModelInstallError) as error:
        return {**result, 'state':'unsupported','error':str(error)}
    try:
        verified_model_bytes(base)
        result.update(state='installed',installed=True,checkpoint_verified=True)
        proof = base/'readiness.json'
        if proof.exists():
            receipt = json.loads(_read_regular(proof,65536))
            if receipt == {'probe':PROBE,'runtime':identity}:
                result.update(ready=True,readiness='cpu-probe-passed')
            else:
                result.update(readiness='stale',error='Runtime changed; explicitly recheck CPU readiness')
    except FileNotFoundError:
        pass
    except (OSError, ValueError, RuntimeError) as error:
        result.update(state='invalid',error=str(error),ready=False)
    return result


def _emit(progress, phase, **values):
    if progress:
        progress({'extension_id':M.EXTENSION_ID,'model_id':M.MODEL_ID,'phase':phase,**values})


def check_readiness(root=None, *, cancelled=None, progress=None, _owned=False):
    from .hand_shape_model import verified_model_bytes, _read_regular
    base = _base(root)
    if not _owned:
        owner = _lock_model(base)
        try:
            return check_readiness(base,cancelled=cancelled,progress=progress,_owned=True)
        finally:
            owner.close()
    identity = _identity()
    verified_model_bytes(base)
    (base/'readiness.json').unlink(missing_ok=True)
    _emit(progress,'readiness',ready=False)
    with tempfile.TemporaryDirectory(prefix='.hand-probe-',dir=base.parent) as directory:
        output = Path(directory)/'result.json'
        _run([sys.executable,'-B','-m','lumaretouch_engine.hand_shape_setup','--probe',
              '--root',str(base),'--output',str(output)],cancelled,Path(directory)/'probe.log',timeout=90)
        expected = {'probe':PROBE,'runtime':identity}
        if json.loads(_read_regular(output,65536)) != expected or _identity() != identity:
            raise ModelInstallError('Hand CPU probe identity changed or did not match')
        verified_model_bytes(base)
        _cancel(cancelled)
        receipt = Path(directory)/'readiness.json'
        receipt.write_text(json.dumps(expected,sort_keys=True))
        os.replace(receipt,base/'readiness.json')
    return model_status(base)


def install_model(root=None, *, cancelled=None, progress=None):
    from .curated_extension_download import acquire
    from .hand_shape_model import verified_model_bytes, _read_regular
    base = _base(root)
    _identity()  # Missing base runtime is explicit, before any network.
    owner = _lock_model(base)
    try:
        _cancel(cancelled)
        if model_status(base)['installed']:
            return check_readiness(base,cancelled=cancelled,progress=progress,_owned=True)
        if shutil.disk_usage(base.parent).free < 64*1024*1024:
            raise ModelInstallError('Hand setup needs 64 MiB free staging space')
        partial = acquire(base,profile=M,cancelled=lambda:_cancel(cancelled),
                          emit=lambda phase,**values:_emit(progress,phase,**values))
        with tempfile.TemporaryDirectory(prefix='.hand-install-',dir=base.parent) as directory:
            stage = Path(directory)
            data = _read_regular(partial,M.MODEL_SIZE_BYTES,exact_size=M.MODEL_SIZE_BYTES)
            if sha256(data).hexdigest()!=M.MODEL_SHA256:
                raise ModelInstallError('Retained hand asset changed before staging')
            (stage/M.MODEL_FILENAME).write_bytes(data)
            verified_model_bytes(stage)
            candidate = check_readiness(stage,cancelled=cancelled,progress=progress,_owned=True)
            if not candidate['ready']:
                raise ModelInstallError('Hand candidate failed CPU capability check')
            _cancel(cancelled)
            _base(base)  # Reject a substituted symlink before publication.
            base.mkdir(exist_ok=True)
            # Never publish readiness before bytes; interruption fails closed.
            (base/'readiness.json').unlink(missing_ok=True)
            os.replace(stage/M.MODEL_FILENAME,base/M.MODEL_FILENAME)
            os.replace(stage/'readiness.json',base/'readiness.json')
        return model_status(base)
    finally:
        owner.close()


def _probe(root, output):
    # Authored application probe, never executed as development acceptance.
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU,(60,60))
    signal.alarm(75)
    identity = _identity()
    from .hand_shape_model import verified_model_bytes
    data = verified_model_bytes(_base(root))
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode
    from mediapipe.tasks.python.vision import hand_landmarker
    verify_producer_origin(hand_landmarker.__file__,identity)
    options = HandLandmarkerOptions(base_options=BaseOptions(model_asset_buffer=data,
        delegate=BaseOptions.Delegate.CPU),running_mode=RunningMode.IMAGE,num_hands=1)
    with HandLandmarker.create_from_options(options) as detector:
        result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB,data=np.zeros((64,64,3),dtype=np.uint8)))
    if not (len(result.hand_landmarks)==len(result.handedness) and len(result.hand_landmarks)<=1):
        raise ModelInstallError('Hand CPU probe returned an invalid result contract')
    if _identity()!=identity:
        raise ModelInstallError('Hand runtime changed during probe')
    Path(output).write_text(json.dumps({'probe':PROBE,'runtime':identity},sort_keys=True))


def main():
    parser=argparse.ArgumentParser(description='Explicit pinned hand-landmark asset setup')
    actions=parser.add_mutually_exclusive_group(required=True)
    for name in ('install','status','check','probe'):
        actions.add_argument('--'+name,action='store_true')
    parser.add_argument('--root'); parser.add_argument('--output')
    args=parser.parse_args()
    if args.probe:
        if not args.root or not args.output: parser.error('Internal probe requires root and output')
        _probe(args.root,args.output); return 0
    if args.root or args.output: parser.error('Public setup accepts no path or URL overrides')
    stopped=threading.Event()
    for signum in (signal.SIGINT,signal.SIGTERM):
        signal.signal(signum,lambda *_:stopped.set())
    def emit(value): print(json.dumps(value,ensure_ascii=False),flush=True)
    try:
        result = install_model(cancelled=stopped.is_set,progress=emit) if args.install else (
            check_readiness(cancelled=stopped.is_set,progress=emit) if args.check else model_status())
        emit(result); return 0
    except Exception as error:
        emit({'extension_id':M.EXTENSION_ID,'model_id':M.MODEL_ID,
              'state':'cancelled' if isinstance(error,InstallCancelled) else 'error','error':str(error)})
        return 2


if __name__=='__main__':
    raise SystemExit(main())
