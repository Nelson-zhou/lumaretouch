"""Source-bound transfer preflight and shared independent-group raster adapter.

Rendering remains in the existing grade stage, after LUT and before background/
geometry. The pipeline must warp these source-domain masks with the SAME true
deformation grid as the pixels before mixing each group.
"""
from copy import deepcopy
import base64
import io
import json
import numpy as np
from PIL import Image
from . import local_grade_layers as L, local_mask_state as M
from . import local_grade_semantics as S


def prompt_stamp(groups):
    from . import prompted_mask_resolver as P
    if any(layer['enabled'] and P.active(layer['mask']['recipe']) for layer in groups['layers']):
        return json.dumps(P.dependency_stamp(), sort_keys=True)
    return None


def verify_original(groups, row):
    shape = (row['src_h'], row['src_w'])
    L.validate_budget(groups, shape)
    # All groups belong to this one source. Hash it once per verification,
    # rather than twice per enabled group. Never replace a content check with
    # only path equality; the live-gesture lease below is separately guarded.
    enabled = [layer for layer in groups['layers'] if layer['enabled']]
    digest = M.source_digest(row['path']) if any(layer['mask']['source'] for layer in enabled) else None
    verified_models = set()
    for layer in enabled:
        mask, source = layer['mask'], layer['mask']['source']
        if source is not None and ((source['height'], source['width']) != shape or source['sha256'] != digest):
            raise ValueError('局部调色组源图尺寸或 SHA-256 已变化')
        if M.R.dependencies(mask['recipe'])[1]:
            owner = json.dumps(mask['semantic_owner'], sort_keys=True)
            if owner not in verified_models:
                S.model_bytes(mask['semantic_owner'])
                verified_models.add(owner)


def verify_legacy(state, path, shape):
    """Preserving the old slot must not hide an already-missing operand."""
    if state.get('_grade_scope') != 'objects': return
    mask = M.check(state.get('_local_masks'))
    M.verify_source(mask, path, shape)
    M.R.validate_budget(mask['recipe'], shape)
    _, channels = M.R.dependencies(mask['recipe'])
    if channels:
        if mask['semantic_owner'] != M.owner_from_state(state):
            raise ValueError('目标旧对象调色的语义分析未恢复或模型不匹配，请先打开并分析目标')
        S.model_bytes(mask['semantic_owner'])
        fields = getattr(state.get('_precompute'), 'masks', None) or {}
        if any(channel not in fields for channel in channels): raise ValueError('目标旧对象调色缺少启用的语义操作数')
        for channel in channels:
            field = np.asarray(fields[channel])
            if field.ndim != 2 or field.dtype.kind != 'f' or not field.size or not np.isfinite(field).all() or np.any(field<0) or np.any(field>1):
                raise ValueError('目标旧对象调色的语义操作数无效，不能忽略后继续')
    from . import prompted_mask_resolver as P
    if P.active(mask['recipe']):
        # A preserved target prompt is recomputed only on that same target,
        # never treated as portable source data.
        P.fields(mask['recipe'], mask['source'], path, (min(shape[0],256),min(shape[1],256)), force=True)


def rasters(groups, path, shape, *, rgb=None, force=False, cancelled=lambda: False):
    value = L.check(groups)
    L.validate_budget(value, shape)
    result = []
    for layer in value['layers']:
        if not layer['enabled']: continue
        if cancelled(): raise InterruptedError('局部调色组计算已取消')
        mask = layer['mask']
        M.verify_source(mask, path)
        semantic = S.fields(mask, path, shape, force=force, cancelled=cancelled)
        from .prompted_mask_resolver import fields
        semantic.update(fields(mask['recipe'], mask['source'], path, shape, force=force, cancelled=cancelled))
        weight = M.R.raster(mask['recipe'], shape, rgb=rgb, semantic=semantic)
        result.append({'id': layer['id'], 'grade': layer['grade'], 'weight': weight})
    return result


def diagnostic(engine, group_id):
    """The selected saved group's source alpha, never legacy or draft coverage.

    Disabled groups still have editable masks: inspect their saved composition
    without enabling the effect or writing document/history state.
    """
    layer = next((item for item in L.check(engine._local_grade_layers)['layers']
                  if item['id'] == group_id), None)
    if layer is None: raise ValueError('所选局部调色组已不存在，请重新选择')
    pipe = engine._vram
    groups = {'version':L.VERSION, 'layers':[{**layer, 'enabled':True}]}
    try:
        row = engine._docs[engine._doc_index]
        if row.get('_local_source_stamp') != M.file_stamp(row['path']):
            raise ValueError('源文件在解码后变化，请重新打开照片')
        verify_original(groups, row)
        rgb = pipe.src_f32[0].permute(1,2,0).detach().cpu().numpy()
        return rasters(groups, row['path'], (pipe.h,pipe.w), rgb=rgb)[0]['weight'], None
    except Exception as error:
        return np.zeros((pipe.h,pipe.w), np.uint8), str(error)[:2000]


def prepare_modules(state, modules, row, transfer_options, *, preview=False):
    """Read-only preflight: freeze each target's own source, model and full budget.

    The thumbnail is explicitly a source-mask coverage diagnostic, never proof
    of full-resolution pixels or final repaired/deformed target appearance.
    """
    if L.OP not in modules: return deepcopy(modules), None
    from .decode import load_rgb
    path = row['path']
    before = M.file_stamp(path)
    digest = M.source_digest(path)
    decoded = load_rgb(path, 256 * 256)
    if before != M.file_stamp(path): raise ValueError('目标源文件在预检解码时变化，请重新预检')
    binding = {'sha256': digest, 'width': decoded.src_w, 'height': decoded.src_h}
    local, facts = L.transfer(modules[L.OP], state, binding, transfer_options)
    if facts['legacy_preserved']: verify_legacy(state, path, (decoded.src_h, decoded.src_w))
    L.validate_budget(local['groups'], (decoded.src_h, decoded.src_w))
    # Force semantic inference separately for every target at review time. Its
    # compact cache contains only probabilities keyed by target hash+model hash.
    rastered = rasters(local['groups'], path, (decoded.h, decoded.w),
                      rgb=np.asarray(decoded.rgb, np.float32) / 255.0, force=True)
    if before != M.file_stamp(path): raise ValueError('目标源文件在蒙版预检时变化，请重新预检')
    facts.update(source_stamp=list(before), preview_domain='original-source-rgb8-coverage',
                 prompted_dependencies=prompt_stamp(local['groups']),
                 full_dimensions=[decoded.src_w, decoded.src_h],
                 groups=[{'id': item['id'], 'covered_proxy_pixels': int(np.count_nonzero(item['weight']))}
                         for item in rastered])
    if preview:
        coverage = np.maximum.reduce([item['weight'] for item in rastered]) if rastered else np.zeros((decoded.h, decoded.w), np.uint8)
        color = np.asarray(decoded.rgb, np.float32)
        alpha = np.asarray(coverage, np.float32)[..., None] / 255.0 * .45
        pixels = np.rint(color * (1-alpha) + np.array([0, 220, 235], np.float32) * alpha).astype(np.uint8)
        stream = io.BytesIO(); Image.fromarray(pixels).save(stream, format='JPEG', quality=70)
        raw = stream.getvalue()
        if len(raw) > 65536: raise ValueError('局部蒙版预检缩略图超过 64 KiB 预算')
        facts['preview_jpeg'] = base64.b64encode(raw).decode('ascii')
    prepared = deepcopy(modules); prepared[L.OP] = local
    return prepared, facts


def verify_modules(modules, row, facts):
    if L.OP not in modules: return
    if type(facts) is not dict or list(M.file_stamp(row['path'])) != facts.get('source_stamp'):
        raise ValueError('目标源文件在预检后变化，请重新预检')
    groups = L.check_params(modules[L.OP])['groups']
    S.verify(groups, row['path'])
    if prompt_stamp(groups) != facts.get('prompted_dependencies'): raise ValueError('保留的 AI 提示组依赖已变化，请重新预检')
    for layer in groups['layers']:
        if layer['enabled']: M.verify_source(layer['mask'], row['path'], tuple(reversed(facts['full_dimensions'])))
    L.validate_budget(groups, tuple(reversed(facts['full_dimensions'])))
    if facts.get('legacy_preserved'): verify_legacy(row['state'], row['path'], tuple(reversed(facts['full_dimensions'])))


def sync(engine, *, strict=False):
    pipe = engine._vram
    if pipe is None: return
    groups = L.check(getattr(engine, '_local_grade_layers', None))
    if not groups['layers']:
        pipe.local_grade_layers.set([])
        pipe._local_grade_layers_key = None
        pipe._local_grade_masks_key = None
        return
    row = engine._docs[engine._doc_index]
    key = None
    try:
        live = engine.__dict__.get('_local_grade_live_owner')
        if live is not None and live.cached_sync(groups):
            return  # Full SHA verification at admission/commit, guarded lease only.
        stamp = M.file_stamp(row['path'])
        if row.get('_local_source_stamp') != stamp: raise ValueError('源文件在解码后变化，请重新打开照片')
        # Model bytes are checked even on a cache hit. Replacing a model cannot
        # leave previously rendered semantic weights masquerading as current.
        verify_original(groups, row)
        dependencies = prompt_stamp(groups)
        key = (json.dumps(groups, sort_keys=True), stamp, id(pipe.src_f32), dependencies)
        if getattr(pipe, '_local_grade_layers_key', None) == key:
            if strict and pipe.local_grade_layers.suspended: raise ValueError(pipe.local_grade_layers.suspended)
            return
        masks = [{k: layer[k] for k in ('id', 'enabled', 'mask')} for layer in groups['layers']]
        masks_key = (json.dumps(masks, sort_keys=True), stamp, id(pipe.src_f32),
                     id(pipe.local_grade_layers), dependencies)
        if (not pipe.local_grade_layers.suspended
                and getattr(pipe, '_local_grade_masks_key', None) == masks_key):
            # A numeric/name-only commit keeps the existing verified coverage.
            # No CPU raster, semantic inference or tensor upload is needed.
            pipe.local_grade_layers.set_parameters(groups)
            pipe._local_grade_layers_key = key
            return
        rgb = pipe.src_f32[0].permute(1, 2, 0).detach().cpu().numpy()
        fields = rasters(groups, row['path'], (pipe.h, pipe.w), rgb=rgb)
        pipe.local_grade_layers.set(fields)
        pipe._local_grade_layers_key = key
        pipe._local_grade_masks_key = masks_key
    except Exception as error:
        pipe.local_grade_layers.set([], reason=str(error))
        pipe._local_grade_layers_key = key
        pipe._local_grade_masks_key = None
        if strict: raise


def export_prepare(spec, source, *, cancelled=lambda: False):
    groups = L.check(spec.local_grade_groups)
    if not groups['layers']:
        spec.local_grade_fields = []
        return
    if not spec.local_mask_source_path: raise ValueError('独立局部调色组缺少原图路径，导出已阻止')
    for layer in groups['layers']:
        M.verify_source(layer['mask'], spec.local_mask_source_path, source.shape[:2])
    spec.local_grade_fields = rasters(groups, spec.local_mask_source_path, source.shape[:2], rgb=source,
                                     force=True, cancelled=cancelled)
