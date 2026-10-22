"""Local lossless frozen-reference bundle, content addressed and bounded.

Owner selects an existing project-owned asset directory. No external paths are
stored in recipes; no upload/download. Bundles need inclusion in project save/
restore and portable-preset packaging before reference intent is enabled there.
"""
from hashlib import sha256
from pathlib import Path
import json
import math
import os
import tempfile
import zipfile
import numpy as np
from .reference_color_review import ColorInput,validate,identity
from . import reference_color_state as S
MAX_BYTES=256*1024*1024
MAX_PIXELS=32_000_000
MAX_RAW_BYTES=MAX_PIXELS*13+16_384


def _hash(path):
    h=sha256()
    with open(path,'rb') as stream:
        while chunk:=stream.read(1024*1024): h.update(chunk)
    return h.hexdigest()


def save(root,frame):
    rgb=validate(frame)
    if rgb.shape[0]*rgb.shape[1]>MAX_PIXELS: raise ValueError('完整参考图超过本地样片预算；不会静默降为8位或缩小原片')
    root=Path(root)
    if not root.is_dir(): raise ValueError('项目样片目录未准备好')
    meta=identity(frame,rgb);meta['domain']=frame.domain
    raw=json.dumps(meta,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    fd,name=tempfile.mkstemp(prefix='.reference-',suffix='.npz',dir=root)
    try:
        with os.fdopen(fd,'wb') as stream:
            np.savez_compressed(stream,rgb=rgb,authentic=frame.authentic_mask,metadata=np.frombuffer(raw,np.uint8))
            stream.flush();os.fsync(stream.fileno())
        if os.path.getsize(name)>MAX_BYTES: raise ValueError('参考图资源超过保存预算')
        asset_id=_hash(name);destination=root/(asset_id+'.npz')
        if destination.exists():
            if _hash(destination)!=asset_id: raise ValueError('既有参考资源损坏')
            os.unlink(name)
        else: os.replace(name,destination)
        return {'source':frame.source,'render_sha256':meta['render_sha256'],'asset_id':asset_id}
    finally:
        if os.path.exists(name):os.unlink(name)


def load(root,reference):
    test=S.empty();test['reference']=reference;S.check(test)
    path=Path(root)/(reference['asset_id']+'.npz')
    if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_BYTES:
        raise ValueError('参考图本地资源缺失/不安全/超过预算')
    if _hash(path)!=reference['asset_id']: raise ValueError('参考图本地资源内容变化')
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        if {e.filename for e in entries}!={'rgb.npy','authentic.npy','metadata.npy'} or len(entries)!=3 or sum(e.file_size for e in entries)>MAX_RAW_BYTES:
            raise ValueError('参考图压缩包目录或解压预算无效')
        # Validate declared NPY dimensions before NumPy allocates any array.
        for entry in entries:
            with archive.open(entry) as stream:
                version=np.lib.format.read_magic(stream)
                if version==(1,0): shape,order,dtype=np.lib.format.read_array_header_1_0(stream)
                elif version==(2,0): shape,order,dtype=np.lib.format.read_array_header_2_0(stream)
                else: raise ValueError('参考资源 NPY 版本不支持')
                size=math.prod(shape)*dtype.itemsize
                expected={'rgb.npy':np.dtype('float32'),'authentic.npy':np.dtype('bool'),'metadata.npy':np.dtype('uint8')}[entry.filename]
                if dtype!=expected or order or any(type(n) is not int or n<1 for n in shape) or size>MAX_RAW_BYTES or stream.tell()+size!=entry.file_size:
                    raise ValueError('参考资源数组头或内存预算无效')
                if entry.filename=='rgb.npy' and (len(shape)!=3 or shape[-1]!=3 or math.prod(shape[:2])>MAX_PIXELS):
                    raise ValueError('参考资源 RGB 尺寸超限')
                if entry.filename=='metadata.npy' and (len(shape)!=1 or size>8192):
                    raise ValueError('参考资源元数据尺寸超限')
    with np.load(path,allow_pickle=False) as bundle:
        rgb=bundle['rgb'];mask=bundle['authentic'];raw=bundle['metadata']
        if raw.dtype!=np.uint8 or raw.ndim!=1 or raw.size>8192: raise ValueError('参考图元数据无效')
        meta=json.loads(raw.tobytes())
    fields={'document_id','revision','source','state_key','render_sha256','authentic_mask_sha256','domain'}
    if type(meta) is not dict or set(meta)!=fields or meta['domain']!=S.DOMAIN:
        raise ValueError('参考图元数据版本无效')
    if rgb.dtype!=np.float32 or rgb.ndim!=3 or rgb.shape[0]*rgb.shape[1]>MAX_PIXELS:
        raise ValueError('参考图不是保留全精度的有界RGB画布')
    frame=ColorInput(meta['document_id'],meta['revision'],meta['source'],meta['state_key'],rgb,mask)
    normalized=validate(frame)
    if identity(frame,normalized)!={k:v for k,v in meta.items() if k!='domain'}:
        raise ValueError('参考图像素/来源支持与保存摘要不同')
    if meta['source']!=reference['source'] or meta['render_sha256']!=reference['render_sha256']:
        raise ValueError('参考资源与配方中的样片不同')
    if _hash(path)!=reference['asset_id']: raise ValueError('读取参考资源时文件发生变化')
    return frame


def cache_root():
    from .preset_store import preset_dir
    root=Path(preset_dir()).parent/'reference-color'
    root.mkdir(parents=True,exist_ok=True)
    return root


from functools import lru_cache

@lru_cache(maxsize=1)
def _bundle(asset_id):
    path=cache_root()/(asset_id+'.npz')
    if path.is_symlink() or _hash(path)!=asset_id or path.stat().st_size>MAX_BYTES:raise ValueError('参考资源改变')
    raw=np.fromfile(path,dtype=np.uint8);raw.setflags(write=False)
    return [raw[i:i+7_000_000] for i in range(0,len(raw),7_000_000)]


def bundle(reference):
    root=cache_root();load(root,reference)
    return _bundle(reference['asset_id'])


def hydrate(reference,raw):
    if reference is None:return
    if raw is None:
        load(cache_root(),reference);return
    if type(raw) is not list or not raw or len(raw)>40 or any(type(a) is not np.ndarray or a.dtype!=np.uint8 or a.ndim!=1 or not 0<a.size<=7_000_000 for a in raw) or sum(a.size for a in raw)>MAX_BYTES:
        raise ValueError('项目参考图资源分块无效')
    digest=sha256()
    for part in raw:digest.update(memoryview(part))
    if digest.hexdigest()!=reference['asset_id']:raise ValueError('项目参考图资源摘要不同')
    root=cache_root();destination=root/(reference['asset_id']+'.npz')
    if not destination.exists():
        fd,name=tempfile.mkstemp(prefix='.restore-',dir=root)
        try:
            with os.fdopen(fd,'wb') as stream:
                for part in raw:stream.write(memoryview(part))
                stream.flush();os.fsync(stream.fileno())
            os.replace(name,destination)
        finally:
            if os.path.exists(name):os.unlink(name)
    load(root,reference)
