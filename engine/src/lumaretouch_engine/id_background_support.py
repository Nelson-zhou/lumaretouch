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
            or type(raw['version']) is not int or raw['version'] != 1
            or raw['category'] != category or category not in CATEGORIES
            or raw['reviewed'] is not True):
        raise ValueError('保留范围必须逐类独立确认源图范围')
    mask = M.check(raw['mask'])
    if mask['source'] is None or not mask['recipe']['objects'] or mask['semantic_owner'] is not None:
        raise ValueError('需手动源图范围或经确认的提示蒙版，不能自动推断接触关系')
    for obj in mask['recipe']['objects']:
        if obj['kind'] == 'automatic_foreground' and (category != 'subject' or obj['selection']['source'] != mask['source']):
            raise ValueError('自动人像类别建议仅供当前源图主体审核，不证明接触物或完整关联范围')
        if obj['kind'] in ('semantic', 'full'):
            raise ValueError('通用语义或全图范围不能充当独立审核的证件照保留范围')
    if raw['recipe_sha256'] != digest(mask): raise ValueError('保留范围审核摘要不匹配')
    return deepcopy({**raw, 'mask': mask})

def review(engine, category, ids, reviewed):
    if (reviewed is not True or category not in CATEGORIES or type(ids) is not list or not ids
            or any(type(ident) is not str for ident in ids) or len(set(ids)) != len(ids)):
        raise ValueError('请在源图检查后明确确认所选范围')
    from . import creative_derived_source as D
    source = D.binding(engine); local = M.check(engine._local_masks)
    if local['source'] != source: raise ValueError('局部范围不属于当前源图')
    objects = [o for o in local['recipe']['objects'] if o['id'] in ids]
    if len(objects) != len(ids): raise ValueError('所选范围已变化，请重新检查')
    mask = M.check({'source': source, 'semantic_owner': None, 'recipe': {**local['recipe'], 'objects': objects}})
    value = check_binding({'version':1,'category':category,'reviewed':True,'mask':mask,'recipe_sha256':digest(mask)}, category)
    from . import prompted_mask_resolver as P
    row = engine._docs[engine._doc_index]
    if D.record(engine) is None:
        # Disabled selected automatic operands also retain verified provenance.
        for obj in objects:
            if obj['kind'] == 'automatic_foreground':
                P.fields({**mask['recipe'],'objects':[{**obj,'enabled':True}]},source,row['path'],(engine._vram.h,engine._vram.w),force=True)
        P.fields(mask['recipe'],source,row['path'],(engine._vram.h,engine._vram.w))
    else:
        # Review the exact current vectors, not an original-file surrogate or a
        # synthetic subject/contact/hair class. No retained object is rewritten.
        from .creative_derived_id_background import preview
        _,rgb,review_key = preview(engine)
        R.validate_budget(mask['recipe'],(source['height'],source['width']))
        prompted = [o for o in objects if o['kind'] == 'prompted']
        if prompted:
            from .creative_derived_prompted import capture
            packet = capture(engine)
            _prompted_input(mask,source,packet)
            # Disabled chosen operands still need valid review evidence. Resolve
            # one at a time without changing their retained visibility or order.
            dependency = P.dependency_stamp()
            for obj in prompted:
                stack = {**mask['recipe'],'objects':[{**obj,'enabled':True}]}
                P.fields(stack,source,None,rgb.shape[:2],source_input=packet,force=True)
            if P.dependency_stamp() != dependency:
                raise ValueError('提示模型在保留范围审核期间变化，请重新检查')
        if preview(engine)[2] != review_key:
            raise ValueError('保留范围审核期间源图或当前文档管线变化，请重新检查')
    # Field resolution may outlive a document/local-object edit. The review is
    # valid only for the exact current chosen objects in their composition order.
    D.verify(source,engine)
    current = M.check(engine._local_masks)
    if current['source'] != source or [o for o in current['recipe']['objects'] if o['id'] in ids] != objects:
        raise ValueError('所选范围在审核期间变化，请重新检查')
    return value


def _prompted_input(mask, effective_source, packet):
    """Validate retained selections against owned canonical model-only bytes."""
    from .creative_derived_prompted import validate
    validate(packet,effective_source)
    expected = packet['descriptor']['input_sha256']
    if any(obj['kind'] == 'prompted' and obj['selection']['input_sha256'] != expected
           for obj in mask['recipe']['objects']):
        raise ValueError('提示保留范围不属于当前不可变源图输入')


def raster(binding, path, source, *, full_source=False, cancelled=lambda:False,
           effective_source=None, source_input=None, source_pixels=None, force_prompted=False):
    """Raster exact support against an explicit native or derived input route.

    The caller proves derived pixels with its live/source-export owner. Preview
    RGB is never used to manufacture model input; export keeps its actual full
    float32 RGB, independently of the final file's chosen output bit depth.
    """
    import numpy as np
    value = check_binding(binding, binding['category']); mask=value['mask']
    if type(full_source) is not bool or type(force_prompted) is not bool:
        raise ValueError('保留范围重放模式无效')
    if cancelled(): raise InterruptedError('保留范围准备已取消')
    if effective_source is None:
        if path is None or source_input is not None or source_pixels is not None:
            raise ValueError('原照片保留范围必须使用原图路径，不能混用派生输入')
        M.verify_source(mask,path)
    else:
        if path is not None:
            raise ValueError('派生保留范围不能回退到原照片路径')
        expected = M.check({'source':effective_source,'semantic_owner':None,'recipe':M.empty()['recipe']})['source']
        if expected != mask['source']:
            raise ValueError('保留范围属于另一张有效源图')
        rgb = np.asarray(source)
        if (rgb.dtype != np.float32 or rgb.ndim != 3 or rgb.shape[2] != 3
                or min(rgb.shape[:2]) < 1 or rgb.shape[0] > expected['height'] or rgb.shape[1] > expected['width']):
            raise ValueError('派生保留范围需要当前源图的浮点 RGB 输入')
        for y in range(0,rgb.shape[0],128):
            if cancelled(): raise InterruptedError('保留范围准备已取消')
            block=rgb[y:y+128]
            if not np.isfinite(block).all() or np.any(block < 0) or np.any(block > 1):
                raise ValueError('派生保留范围不能静默裁切 HDR 或非有限像素')
        if full_source:
            if (rgb.shape[:2] != (expected['height'],expected['width'])
                    or source_pixels is not source or source_input is not None):
                raise ValueError('保留范围导出必须使用同一完整浮点源图，不能使用代理或模型副本')
        elif source_pixels is not None:
            raise ValueError('代理保留范围不能充当完整模型输入')
        from . import prompted_mask_resolver as P
        if source_input is not None:
            _prompted_input(mask,expected,source_input)
        elif not full_source and P.active(mask['recipe']):
            raise ValueError('派生提示保留范围缺少规范源图模型输入')
    if cancelled(): raise InterruptedError('保留范围准备已取消')
    from .prompted_mask_resolver import fields
    semantic=fields(mask['recipe'],mask['source'],path,source.shape[:2],
                    force=full_source or force_prompted,cancelled=cancelled,
                    source_input=source_input,source_pixels=source_pixels)
    out=R.raster(mask['recipe'],source.shape[:2],rgb=source,semantic=semantic)
    if cancelled(): raise InterruptedError('保留范围准备已取消')
    return out.astype(np.float32)/255.0
