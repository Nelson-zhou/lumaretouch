# SPDX-License-Identifier: GPL-3.0-or-later
"""Retained applied parameters/masks replay without model availability."""
from . import semantic_colour_state as S, semantic_colour_assets as MA
BUNDLE='_semantic_colour_bundle'

def validate_records(value, *, allowed=True, assets=None, checked=None):
    checked=set() if checked is None else checked
    if isinstance(value,dict):
        if S.KEY in value:
            if not allowed:raise ValueError('渲染画布语义追色必须使用工程 v12，不能写在旧 schema 下')
            recipe=S.check(value[S.KEY]);bundle=value.get(BUNDLE)
            MA.check(recipe,value.get(MA.KEY,{}),encoded=True)
            if recipe['enabled'] and recipe['last_review'] is None:raise ValueError('AI 追色工程缺少初始冻结审核摘要')
            if recipe['reference'] is not None and not bundle:raise ValueError('AI 追色工程缺少完整保留样片资源，不能悄悄丢失参考')
            if bundle is not None and (type(bundle) is not list or not 1<=len(bundle)<=40):raise ValueError('AI 追色工程参考资源分块无效')
            if assets is not None:_validate_encoded_assets(recipe,bundle,value.get(MA.KEY,{}),assets,checked)
        for child in value.values():validate_records(child,allowed=allowed,assets=assets,checked=checked)
    elif isinstance(value,list):
        for child in value:validate_records(child,allowed=allowed,assets=assets,checked=checked)

def migrate(value,*,root=False):
    if isinstance(value,dict):
        for child in list(value.values()):migrate(child)
        if root or '_strength' in value or '_reference_color' in value:
            value.setdefault(S.KEY,S.empty());value.setdefault(BUNDLE,None);value.setdefault(MA.KEY,{})
    elif isinstance(value,list):
        for child in value:migrate(child)


def validate_decoded(state):
    """Hard asset integrity at restore; no ML, decoder, or reference materialization."""
    recipe=S.check(state.get(S.KEY));assets=MA.check(recipe,state.get(MA.KEY,{}));bundle=state.get(BUNDLE)
    if recipe['reference'] is not None:
        import numpy as np
        from hashlib import sha256
        from .reference_color_assets import MAX_BYTES
        if type(bundle) is not list or not 1<=len(bundle)<=40 or any(type(a) is not np.ndarray or a.dtype!=np.uint8 or a.ndim!=1 or not 0<a.size<=7_000_000 for a in bundle) or sum(a.size for a in bundle)>MAX_BYTES:
            raise ValueError('AI 追色工程完整样片分块缺失，拒绝只恢复半个配方')
        digest=sha256()
        for part in bundle:digest.update(memoryview(part))
        if digest.hexdigest()!=recipe['reference']['asset_id']:raise ValueError('AI 追色工程完整样片摘要不符')
    if recipe['enabled'] and recipe['last_review'] is None:raise ValueError('AI 追色工程审核摘要缺失')
    return {S.KEY:recipe,BUNDLE:bundle,MA.KEY:assets}


def _raw_asset(ref,assets,limit):
    """Strict raw uint8 resources only, including generic project location metadata."""
    import base64
    from hashlib import sha256
    import numpy as np
    if type(ref) is not dict or set(ref)-{'__asset__','at'} or type(ref.get('__asset__')) is not str or ('at' in ref and type(ref['at']) is not str):
        raise ValueError('AI 追色工程资源引用无效')
    key=ref['__asset__'];row=assets.get(key)
    if not key.startswith('sha256:') or len(key)!=71 or type(row) is not dict or set(row)!={'kind','shape','dtype','bytes','b64'}:
        raise ValueError('AI 追色工程资源缺失')
    size=row['bytes']
    if type(size) is not int or not 0<size<=limit or row['kind']!='raw' or row['dtype']!='uint8' or row['shape']!=[size] or type(row['b64']) is not str or len(row['b64'])>4*((limit+2)//3):
        raise ValueError('AI 追色工程资源必须是有界原始字节')
    raw=base64.b64decode(row['b64'],validate=True)
    if len(raw)!=size or sha256(raw).hexdigest()!=key[7:]:raise ValueError('AI 追色工程资源字节摘要不符')
    return np.frombuffer(raw,np.uint8)


def _validate_encoded_assets(recipe,bundle,mask_assets,assets,checked):
    """Validate inactive versions too, without materializing either photo or running ML."""
    from hashlib import sha256
    from .reference_color_assets import MAX_BYTES
    mask_key=('masks',tuple((m['base']['sha256'],m['base']['width'],m['base']['height']) for m in recipe['masks'] if m['base'] is not None))
    if mask_key not in checked:
        decoded={digest:_raw_asset(ref,assets,1_048_576) for digest,ref in mask_assets.items()}
        MA.check(recipe,decoded);checked.add(mask_key)
    if recipe['reference'] is None:return
    if type(bundle) is not list or not 1<=len(bundle)<=40:raise ValueError('AI 追色工程完整样片分块无效')
    keys=tuple(ref.get('__asset__') if type(ref) is dict else None for ref in bundle)
    if any(type(key) is not str for key in keys):raise ValueError('AI 追色工程完整样片分块引用无效')
    key=('reference',recipe['reference']['asset_id'],keys)
    if key in checked:return
    digest=sha256();size=0
    for ref in bundle:
        chunk=_raw_asset(ref,assets,7_000_000);size+=chunk.size
        if size>MAX_BYTES:raise ValueError('AI 追色工程完整样片超过字节预算')
        digest.update(memoryview(chunk))
    if digest.hexdigest()!=recipe['reference']['asset_id']:raise ValueError('AI 追色工程完整样片摘要不符')
    checked.add(key)
