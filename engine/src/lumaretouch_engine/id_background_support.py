"""Independent, explicit source-reviewed support. Never infer contact from SAM.

Manual vectors replay at the requested source grid. Coverage is quantized by the
existing local-mask rasterizer; this is not automatic hair matting.
"""
from copy import deepcopy
import hashlib
import json
from . import local_mask_state as M, local_mask_recipe as R

CATEGORIES = ('subject', 'contact', 'all')

def digest(mask):
    return hashlib.sha256(json.dumps(mask, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def check_binding(raw, category):
    if (type(raw) is not dict or set(raw) != {'version','category','reviewed','mask','recipe_sha256'}
            or raw['version'] != 1 or raw['category'] != category or category not in CATEGORIES
            or raw['reviewed'] is not True):
        raise ValueError('保留范围必须逐类独立确认源图范围')
    mask = M.check(raw['mask'])
    if mask['source'] is None or not mask['recipe']['objects'] or mask['semantic_owner'] is not None:
        raise ValueError('需手动源图范围或经确认的提示蒙版，不能自动推断接触关系')
    for obj in mask['recipe']['objects']:
        if obj['kind'] in ('semantic', 'full'):
            raise ValueError('通用语义或全图范围不能充当独立审核的证件照保留范围')
    if raw['recipe_sha256'] != digest(mask): raise ValueError('保留范围审核摘要不匹配')
    return deepcopy({**raw, 'mask': mask})

def review(engine, category, ids, reviewed):
    if reviewed is not True or category not in CATEGORIES or type(ids) is not list or not ids or len(set(ids)) != len(ids):
        raise ValueError('请在源图检查后明确确认所选范围')
    source = M.bind_source(engine); local = M.check(engine._local_masks)
    if local['source'] != source: raise ValueError('局部范围不属于当前源图')
    objects = [o for o in local['recipe']['objects'] if o['id'] in ids]
    if len(objects) != len(ids): raise ValueError('所选范围已变化，请重新检查')
    mask = M.check({'source': source, 'semantic_owner': None, 'recipe': {**local['recipe'], 'objects': objects}})
    value = check_binding({'version':1,'category':category,'reviewed':True,'mask':mask,'recipe_sha256':digest(mask)}, category)
    from .prompted_mask_resolver import fields
    row = engine._docs[engine._doc_index]
    # Resolve every immutable prompted artifact before accepting the review.
    fields(mask['recipe'],source,row['path'],(engine._vram.h,engine._vram.w))
    return value

def raster(binding, path, source, *, full_source=False, cancelled=lambda:False):
    import numpy as np
    value = check_binding(binding, binding['category']); mask=value['mask']
    M.verify_source(mask,path)
    if cancelled(): raise InterruptedError('保留范围准备已取消')
    from .prompted_mask_resolver import fields
    semantic=fields(mask['recipe'],mask['source'],path,source.shape[:2],force=full_source,cancelled=cancelled)
    out=R.raster(mask['recipe'],source.shape[:2],rgb=source,semantic=semantic)
    if cancelled(): raise InterruptedError('保留范围准备已取消')
    return out.astype(np.float32)/255.0
