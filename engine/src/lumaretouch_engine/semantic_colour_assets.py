# SPDX-License-Identifier: GPL-3.0-or-later
"""Immutable SHA-addressed mask planes, deduplicated by project asset encoding.

Only bounded raw float32 model supports are cached. No source photos or model
inference are used during hydration/replay. Recipes and public receipts carry
small references; the separate owned asset map never crosses UI IPC.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import os
import tempfile
import numpy as np
from . import semantic_colour_state as S
ENCODING='asset-float32-le-v1'
KEY='_semantic_colour_mask_assets'
MAX_PIXELS=262144


def reference(value):
    if type(value) is not dict or set(value)!={'width','height','sha256','encoding'} or value['encoding']!=ENCODING:
        raise ValueError('AI 追色蒙版资源引用无效')
    if any(type(value[k]) is not int or value[k]<1 for k in ('width','height')) or value['width']*value['height']>MAX_PIXELS:
        raise ValueError('AI 追色蒙版资源网格超限')
    S.digest(value['sha256']);return value


def _checked(value,ref):
    reference(ref)
    if type(value) is not np.ndarray or value.dtype!=np.uint8 or value.ndim!=1 or value.size!=ref['width']*ref['height']*4:
        raise ValueError('AI 追色工程蒙版资源缺失或长度无效')
    if sha256(memoryview(np.ascontiguousarray(value))).hexdigest()!=ref['sha256']:
        raise ValueError('AI 追色工程蒙版摘要不符')
    plane=value.view('<f4').reshape(ref['height'],ref['width'])
    if not np.isfinite(plane).all() or np.any(plane<0) or np.any(plane>1):raise ValueError('AI 追色工程蒙版不是有限概率')
    return value


def _root():
    from .preset_store import preset_dir
    root=Path(preset_dir()).parent/'semantic-colour-masks';root.mkdir(parents=True,exist_ok=True);return root


def read(ref):
    reference(ref);path=_root()/(ref['sha256']+'.f32')
    if path.is_symlink() or not path.is_file() or path.stat().st_size!=ref['width']*ref['height']*4:
        raise ValueError('AI 追色保留蒙版资源不可用；请重新载入完整工程，不会重跑模型代替旧结果')
    raw=path.read_bytes();value=_checked(np.frombuffer(raw,np.uint8),ref)
    return value.view('<f4').reshape(ref['height'],ref['width'])


def publish(ref,value):
    value=_checked(value,ref);root=_root();path=root/(ref['sha256']+'.f32')
    if path.is_symlink():raise ValueError('AI 追色蒙版缓存路径不可安全恢复')
    if path.exists():
        try:read(ref);return
        except ValueError:pass  # Valid project bytes can repair our corrupt cache.
    fd,name=tempfile.mkstemp(prefix='.mask-',dir=root)
    try:
        with os.fdopen(fd,'wb') as handle:
            handle.write(memoryview(np.ascontiguousarray(value)));handle.flush();os.fsync(handle.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def check(recipe,assets,*,encoded=False):
    refs={m['base']['sha256']:reference(m['base']) for m in recipe['masks'] if m['base'] is not None and m['base'].get('encoding')==ENCODING}
    if type(assets) is not dict or set(assets)!=set(refs) or len(assets)>8:raise ValueError('AI 追色工程蒙版引用与独占资源不匹配')
    for digest,ref in refs.items():
        value=assets[digest]
        if encoded and type(value) is dict and set(value)<= {'__asset__','at'} and value.get('__asset__')=='sha256:'+digest and ('at' not in value or type(value['at']) is str):continue
        _checked(value,ref)
    return assets


def hydrate(recipe,assets):
    for digest,value in check(recipe,assets).items():
        ref=next(m['base'] for m in recipe['masks'] if m['base'] is not None and m['base']['sha256']==digest)
        publish(ref,value)


def retain(recipe,existing=None):
    """Materialize one private worker proposal or preserve an edited recipe."""
    from . import semantic_colour_masks as M
    out=deepcopy(recipe);assets={};existing=existing or {}
    for mask in out['masks']:
        base=mask['base']
        if base is None:continue
        if base.get('encoding')==ENCODING:
            ref=reference(base)
            value=existing.get(ref['sha256'])
            if value is None:value=np.frombuffer(read(ref).tobytes(),np.uint8)
        else:
            plane=M.unpack(base);ref={k:base[k] for k in ('width','height','sha256')};ref['encoding']=ENCODING
            value=np.frombuffer(np.ascontiguousarray(plane,dtype='<f4').tobytes(),np.uint8)
        value=_checked(value,ref)
        if value.flags.writeable:value=np.frombuffer(value.tobytes(),np.uint8)
        assets[ref['sha256']]=value;mask['base']=ref
        publish(ref,value)
    check(out,assets);return S.check(out),assets
