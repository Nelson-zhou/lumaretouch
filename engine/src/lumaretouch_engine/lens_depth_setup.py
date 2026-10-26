# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit curated depth setup; offline status, authenticated optional wheels.

AUTHORED / UNRUN. The selected app interpreter and its base CPU image stack are
trusted prerequisites, NOT installed, cryptographically authenticated or replaced
by this extension. Optional code is checked against retained pinned wheel bytes,
not a mutable inventory receipt. No operation runs merely by importing this file.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import signal
import stat
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import zipfile
from . import lens_depth_manifest as M
from .prompted_model_install import ModelInstallError, InstallCancelled, _lock_model, _run, _cancel

EXTENSION = 'lens-depth-v1'
PROBE = 'depth-anything-small-cpu-full-frame-v1'
LOCKFILE = Path(__file__).with_name('lens_depth_runtime_lock.json')
BASE = {'torch':'2.7.1+cpu', 'torchvision':'0.22.1+cpu'}


def root_path(root=None):
    if root is not None:
        value=Path(root)
    else:
        data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
        value=data/'lumaretouch'/'optional-models'/M.MODEL_ID/M.MODEL_REVISION
    if not value.is_absolute() or '..' in value.parts:
        raise ModelInstallError('Depth model root must be absolute without parent traversal')
    return value


def model_root(root=None):
    return root_path(root)/'model'


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _read(path, limit):
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise ModelInstallError('Unsafe or oversized depth artifact: '+Path(path).name)
        data=stream.read(limit+1)
        if len(data)>limit or len(data)!=info.st_size:
            raise ModelInstallError('Depth artifact changed during read')
        return data


def _lock():
    value=json.loads(_read(LOCKFILE,1024*1024))
    if value.get('profile') != 'cpython312-linux-x86_64-cpu-v1' or not value.get('closure_complete'):
        raise ModelInstallError('Depth optional wheel closure has not been verified')
    if value.get('license_eligibility') != 'verified-primary-evidence':
        raise ModelInstallError('Depth optional runtime setup eligibility pending primary license evidence: '+', '.join(value.get('unresolved_license_evidence', [])))
    return value


def _base_identity():
    if sys.platform!='linux' or sys.version_info[:2]!=(3,12) or platform.machine()!='x86_64':
        raise ModelInstallError('Depth v1 requires selected Linux x86_64 CPython 3.12 app runtime')
    libc,version=platform.libc_ver()
    if libc!='glibc' or tuple(map(int,version.split('.')[:2]))<(2,28):
        raise ModelInstallError('Depth v1 requires glibc 2.28 or newer')
    result={'python':str(Path(sys.executable).resolve()),'version':sys.version,'packages':{}}
    for name in ('torch','torchvision','numpy','Pillow'):
        dist=importlib.metadata.distribution(name)
        if name in BASE and dist.version!=BASE[name]:
            raise ModelInstallError('Depth v1 needs existing '+name+'=='+BASE[name]+'; no base replacement')
        if name in ('numpy','Pillow'):
            match=re.fullmatch(r'(\d+)\.(\d+)(?:\.\d+)?',dist.version)
            pair=tuple(map(int,match.groups())) if match else None
            if pair is None or (name=='numpy' and pair<(2,1)) or (name=='Pillow' and not (11,0)<=pair<=(15,0)):
                raise ModelInstallError('Depth base NumPy>=2.1 and Pillow>=11,<=15.0 prerequisites unmet')
        result['packages'][name]={'version':dist.version,'root':str(Path(dist.locate_file('')).resolve()),
            'record_sha256':_hash((dist.read_text('RECORD') or '').encode())}
    return result


def _wheel_members(raw):
    import io
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names=set(); total=0
        for info in archive.infolist():
            if info.is_dir():
                continue
            path=PurePosixPath(info.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in info.filename or str(path)!=info.filename
                    or not path.parts or info.filename in names or info.filename.endswith(('.pth','.pyc'))
                    or any(part.endswith('.data') for part in path.parts)
                    or stat.S_ISLNK(info.external_attr>>16)):
                raise ModelInstallError('Unsupported or unsafe pinned wheel member')
            names.add(info.filename); total+=info.file_size
            if info.file_size>128*1024**2 or total>512*1024**2:
                raise ModelInstallError('Pinned wheel unpacking exceeds its budget')
            yield info.filename, archive.read(info)


def _runtime_inventory(base, *, extract=False):
    lock=_lock(); site=base/'site-packages'; expected={}; tops=set()
    if base.is_symlink() or site.is_symlink() or (base/'wheels').is_symlink():
        raise ModelInstallError('Depth runtime directory cannot be a symlink')
    for pin in lock['wheels']:
        raw=_read(base/'wheels'/pin['filename'],pin['size'])
        if len(raw)!=pin['size'] or _hash(raw)!=pin['sha256']:
            raise ModelInstallError('Retained depth wheel does not match bundled upstream pin')
        for relative,data in _wheel_members(raw):
            if relative in expected:
                raise ModelInstallError('Overlapping optional wheel ownership')
            expected[relative]=_hash(data)
            top=relative.split('/')[0]
            if not top.endswith('.dist-info'):
                tops.add(top.removesuffix('.py'))
            target=site/relative
            if extract:
                target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('xb') as stream: stream.write(data)
            elif _hash(_read(target,len(data)))!=expected[relative]:
                raise ModelInstallError('Installed depth code differs from authenticated wheel: '+relative)
    if not extract:
        actual=set()
        for path in site.rglob('*'):
            if path.is_symlink():
                raise ModelInstallError('Symlink in optional depth runtime')
            if path.is_file(): actual.add(path.relative_to(site).as_posix())
        if actual!=set(expected):
            raise ModelInstallError('Unowned files in depth optional runtime (including bytecode)')
    return {'runtime_sha256':_hash(json.dumps(expected,sort_keys=True).encode()),
            'lock_sha256':_hash(_read(LOCKFILE,1024*1024)), 'base':_base_identity()},tops


def runtime_identity(root=None):
    identity,_=_runtime_inventory(root_path(root))
    return identity


def activate_runtime(root=None):
    base=root_path(root); identity,tops=_runtime_inventory(base); site=(base/'site-packages').resolve()
    for name,module in tuple(sys.modules.items()):
        if name.split('.')[0] in tops:
            location=getattr(module,'__file__',None)
            if not location or not Path(location).resolve().is_relative_to(site):
                raise ModelInstallError('Foreign optional depth module already loaded: '+name)
    if str(site) not in sys.path: sys.path.insert(0,str(site))
    os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'
    return identity


def model_status(root=None):
    status={'extension_id':EXTENSION,'model_id':M.MODEL_ID,'state':'not-installed','installed':False,
        'ready':False,'code':'not-installed','reason':'Explicit model setup is required',
        'download_bytes':sum(p.size_bytes for p in M.MODEL_FILES),'license':'Apache-2.0',
        'automatic_base_runtime_setup':False,'runtime_download_separate':True,'tested_devices':[],
        'inference_acceptance':'UNRUN','readiness_scope':'bounded CPU generated fixture; not photo quality or performance'}
    try:
        _base_identity(); _lock()
        base=root_path(root)
        if not base.exists(): return status
        from .lens_depth_adapter import _read_model_bytes
        _read_model_bytes(model_root(root),None)
        identity=runtime_identity(root)
        status.update(state='installed',installed=True,code='readiness-required',reason='Explicit CPU readiness check required')
        proof=base/'readiness.json'
        if proof.exists() and json.loads(_read(proof,65536))=={'probe':PROBE,'runtime':identity}:
            status.update(ready=True,code='ready',reason='Bounded CPU readiness passed; photographic acceptance remains UNRUN')
    except Exception as error:
        status.update(state='unsupported',code='unavailable',reason=str(error)[:1024])
    return status


def _emit(progress,phase,**values):
    if progress: progress({'extension_id':EXTENSION,'model_id':M.MODEL_ID,'phase':phase,**values})


def check_readiness(root=None,*,cancelled=None,progress=None,_owned=False):
    base=root_path(root)
    if not _owned:
        owner=_lock_model(base)
        try:return check_readiness(root,cancelled=cancelled,progress=progress,_owned=True)
        finally:owner.close()
    identity=runtime_identity(root)
    (base/'readiness.json').unlink(missing_ok=True)
    _emit(progress,'readiness',ready=False)
    with tempfile.TemporaryDirectory(prefix='.depth-probe-',dir=base.parent) as directory:
        output=Path(directory)/'result.json'
        _run([sys.executable,'-B','-m','lumaretouch_engine.lens_depth_worker','--root',str(base.resolve()),
              '--output',str(output),'--probe','--parent-pid',str(os.getpid())],cancelled,Path(directory)/'probe.log',timeout=110)
        expected={'probe':PROBE,'runtime':identity}
        if json.loads(_read(output,65536))!=expected or runtime_identity(root)!=identity:
            raise ModelInstallError('Depth CPU probe did not verify the installed runtime')
        _cancel(cancelled)
        temporary=Path(directory)/'readiness.json'; temporary.write_text(json.dumps(expected,sort_keys=True))
        os.replace(temporary,base/'readiness.json')
    return model_status(root)


def install_model(root=None,*,cancelled=None,progress=None):
    from .curated_extension_download import acquire
    base=root_path(root); _base_identity(); lock=_lock(); owner=_lock_model(base); staging=None
    try:
        if base.is_symlink(): raise ModelInstallError('Depth destination cannot be a symlink')
        if model_status(root)['installed']:
            return check_readiness(root,cancelled=cancelled,progress=progress,_owned=True)
        if shutil.disk_usage(base.parent).free<2*1024**3:
            raise ModelInstallError('Depth setup needs at least 2 GiB free staging space')
        staging=Path(tempfile.mkdtemp(prefix='.depth-install-',dir=base.parent))
        (staging/'model').mkdir(); (staging/'wheels').mkdir()
        for pin in M.MODEL_FILES:
            profile=SimpleNamespace(CHECKPOINT_SHA256=pin.sha256,CHECKPOINT_SIZE_BYTES=pin.size_bytes,
                CHECKPOINT_URL=M.MODEL_CARD_URL+'/resolve/'+M.MODEL_REVISION+'/'+pin.filename)
            source=acquire(base,emit=lambda phase,**values:_emit(progress,phase,**values),
                cancelled=lambda:_cancel(cancelled),profile=profile)
            shutil.copyfile(source,staging/'model'/pin.filename)
        requirements=staging/'requirements.txt'
        requirements.write_text('\n'.join(p['url']+' --hash=sha256:'+p['sha256'] for p in lock['wheels'])+'\n')
        _emit(progress,'runtime',message='Fetching exact optional wheels; selected base CPU runtime is unchanged')
        _run([sys.executable,'-m','pip','--isolated','download','--no-deps','--only-binary=:all:',
              '--require-hashes','--dest',str(staging/'wheels'),'-r',str(requirements)],cancelled,staging/'install.log')
        _runtime_inventory(staging,extract=True)
        check_readiness(staging,cancelled=cancelled,progress=progress,_owned=True)
        _cancel(cancelled); previous=None
        if base.exists():
            previous=base.parent/(base.name+'.retained-'+str(time.time_ns())); base.rename(previous)
        try:staging.rename(base)
        except Exception:
            if previous is not None and not base.exists():previous.rename(base)
            raise
        staging=None; result=model_status(root); _emit(progress,'complete',**result); return result
    finally:
        if staging is not None:shutil.rmtree(staging,ignore_errors=True)
        owner.close()


def main():
    parser=argparse.ArgumentParser(description='Explicit Depth Anything V2 Small curated setup')
    choice=parser.add_mutually_exclusive_group(required=True)
    for action in ('install','status','check'):choice.add_argument('--'+action,action='store_true')
    args=parser.parse_args(); stopped=threading.Event()
    for signum in (signal.SIGINT,signal.SIGTERM):signal.signal(signum,lambda *_:stopped.set())
    emit=lambda value:print(json.dumps(value,ensure_ascii=False),flush=True)
    try:
        result=install_model(cancelled=stopped.is_set,progress=emit) if args.install else check_readiness(cancelled=stopped.is_set,progress=emit) if args.check else model_status()
        emit(result);return 0
    except Exception as error:
        emit({'extension_id':EXTENSION,'model_id':M.MODEL_ID,'state':'cancelled' if isinstance(error,InstallCancelled) else 'error','ready':False,'error':str(error)});return 2

if __name__=='__main__':raise SystemExit(main())
