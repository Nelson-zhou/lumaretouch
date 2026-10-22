"""Full source validation, bounded preparation and common preview/export stage."""
from copy import deepcopy
import json
import numpy as np
from . import sky_replacement_state as S, sky_replacement_assets as A, local_mask_state as B
from .ops import sky_replacement as O
from .sky_replacement_stage import SkyReplacementStage


def raster(value, shape, *, cancelled=lambda: False):
    value = S.check(value)
    S.validate_budget(value, shape)
    from .cpu_memory_budget import available_estimate
    # Masks + signed distances + Gaussian temporaries. Assets admitted separately.
    if shape[0]*shape[1]*40 + 32*1024**2 > max(0,available_estimate()-256*1024**2)*.65:
        raise ValueError('换天空区域计算内存不足；不放大代理蒙版用于导出')
    fields = {}
    for key, stack in [*value['regions'].items(), ('recovery', value['recovery'])]:
        if cancelled():
            raise InterruptedError('换天空区域计算已取消')
        fields[key] = B.R.raster(stack, shape)
    if value['enabled']:
        if not np.any(fields['sky']) or np.all(fields['sky'] > 254):
            raise ValueError('天空标记为空或覆盖全幅；请明确标记真实天空')
        if value['person_mode'] == 'marked' and not np.any(fields['person']):
            raise ValueError('人物标记已被擦空，请重新标记或声明无人')
        if value['parameters']['reflection'] > 0:
            h = shape[0]
            below = (np.arange(h)+.5)/h >= value['horizon']
            if not np.any(fields['water'][below]):
                raise ValueError('地平线下没有明确标记的水面，不能启用反射')
            if np.any(fields['water'][~below] > 1):
                raise ValueError('水面标记跨过地平线，请调整标记或地平线位置')
    return fields


def prepare(value, shape, *, asset=None, cancelled=lambda: False):
    value = S.check(value)
    S.ready(value)
    raw = raster(value, shape, cancelled=cancelled)
    prepared = {'value': value, 'shape': tuple(shape), 'raw_fields': raw, 'fields': None}
    if not value['enabled']:
        return prepared
    from .cpu_memory_budget import available_estimate
    asset_pixels = value['asset']['width']*value['asset']['height']
    if shape[0]*shape[1]*32 + asset_pixels*64 + 32*1024**2 > max(0,available_estimate()-256*1024**2)*.65:
        raise ValueError('天空浮点处理超过当前内存预算；不会减小全尺寸素材或使用显示代理导出')
    if asset is None:
        asset = A.read(value['asset']['path'], expected=value['asset'], cancelled=cancelled)
    if asset.binding != value['asset'] or B.file_stamp(asset.binding['path']) != asset.stamp:
        raise ValueError('天空素材缓存已经过期')
    if cancelled():
        raise InterruptedError('换天空准备已取消')
    fields = {key: v.astype(np.float32)/255. for key,v in raw.items()}
    fields['sky'] = O.sky_edge(raw['sky'], value['parameters'])
    sky, reflection, tint, cover = O.adjusted_asset(asset.pixels, value['parameters'], shape)
    if cancelled():
        raise InterruptedError('天空效果计算已取消')
    if B.file_stamp(asset.binding['path']) != asset.stamp:
        raise ValueError('天空素材在效果准备期间变化')
    prepared.update(fields=fields, asset=sky, reflection=reflection, tint=tint, cover=cover, asset_stamp=asset.stamp)
    return prepared


def verified_value(engine, value):
    value = S.check(value)
    row = engine._docs[engine._doc_index]
    before = B.file_stamp(row['path'])
    if row.get('_local_source_stamp') != before:
        raise ValueError('源照片自解码后变化，请重新打开')
    B.verify_source(value, row['path'], (row['src_h'],row['src_w']))
    if value['enabled']:
        A.verify(value['asset'])
        if engine._vram.has_background():
            raise ValueError('换天空与换背景不能同时启用；请先关闭当前换背景')
    if B.file_stamp(row['path']) != before:
        raise ValueError('验证换天空身份时源照片变化')
    return value


def stage_key(engine, value):
    row = engine._docs[engine._doc_index]
    asset = value['asset']
    return (json.dumps(value,sort_keys=True), B.file_stamp(row['path']) if value['enabled'] else None, id(engine._vram.src_f32),
            getattr(engine._vram,'deform_version',None), tuple(sorted(engine._vram.deform_amounts.items())),
            B.file_stamp(asset['path']) if asset and value['enabled'] else None)


def sync(engine, *, strict=False):
    pipe = engine._vram
    if pipe is None:
        return
    value = S.check(getattr(engine,'_sky_replacement',None))
    key = None
    try:
        key = stage_key(engine,value)
        if getattr(pipe,'_sky_replacement_key',None) == key:
            if strict and pipe.sky_replacement.suspended:
                raise ValueError(pipe.sky_replacement.suspended)
            return
        if value["enabled"]: verified_value(engine,value)
        stage = SkyReplacementStage(pipe.device,(pipe.h,pipe.w))
        stage.set(value,prepare(value,(pipe.h,pipe.w)) if value['enabled'] else None)
        pipe.sky_replacement,pipe._sky_replacement_key = stage,key
    except Exception as error:
        stage = SkyReplacementStage(pipe.device,(pipe.h,pipe.w))
        stage.set(value,reason=str(error))
        pipe.sky_replacement,pipe._sky_replacement_key = stage,key
        if strict:
            raise


def report(engine):
    value = S.check(getattr(engine,'_sky_replacement',None))
    stage = getattr(engine._vram,'sky_replacement',None)
    return {'version': S.VERSION, 'enabled': value['enabled'], 'editable': S.editable(value),
            'asset': value['asset'], 'suspended': getattr(stage,'suspended',None),
            'automatic_detection': False, 'working_color': 'encoded-srgb',
            'bytes': stage.resident_bytes() if stage else 0,
            'boundaries': ['请手动标记天空、人物和水面；没有自动天空/水面语义检测，不把人像蒙版反选当天空',
                '人物/景物 -100 保留换天空前对应色彩；0 有基础氛围映射，正向增强',
                '素材由你提供，项目引用原件；缺失或 SHA-256 改变会暂停效果与导出',
                '恢复只撤回换天空、其氛围和水面反射，不撤回其他调色、修补或液化',
                '区域属于原照片；预设只带素材与参数，批量必须逐图已有有效标记']}


def verify_snapshot(snap,path,shape=None):
    value = S.check(snap.get('sky_replacement'))
    if not value['enabled']: return
    before = B.file_stamp(path)
    B.verify_source(value,path,shape)
    if shape is not None:
        S.validate_budget(value,shape)
    if value['enabled']:
        S.ready(value)
        A.verify(value['asset'])
        if (snap.get('_bg') or {}).get('active'):
            raise ValueError('此配方同时启用了换天空与换背景，请先选择一种再导出')
    if B.file_stamp(path) != before:
        raise ValueError('验证换天空快照时源图变化')


def check_export_decode(snap,path,before,shape):
    value = S.check(snap.get('sky_replacement'))
    if not value['enabled']:
        return
    if before is None or B.file_stamp(path) != before:
        raise ValueError('全尺寸解码时换天空源图变化')
    verify_snapshot(snap,path,shape)
    snap['sky_replacement_path'],snap['sky_replacement_stamp'] = path,list(before)


def configure_export(spec,snap,shape,*,for_document):
    value = S.check(snap.get('sky_replacement'))
    if value['enabled'] and not for_document:
        raise ValueError('换天空必须在每张目标照片上绑定其自己的区域；不能跨图复制坐标')
    spec.sky_replacement = value
    spec.sky_replacement_path = snap.get('sky_replacement_path')
    spec.sky_replacement_stamp = snap.get('sky_replacement_stamp')
    spec.sky_replacement_prepared = None
    if value['enabled']:
        if not spec.sky_replacement_path:
            raise ValueError('换天空全尺寸导出缺少已验证的源图')
        verify_snapshot(snap,spec.sky_replacement_path,shape)


def export_prepare(spec,shape,*,cancelled=lambda:False):
    value = S.check(spec.sky_replacement)
    spec.sky_replacement_prepared = None
    if not value['enabled']:
        return
    before = B.file_stamp(spec.sky_replacement_path)
    if list(before) != spec.sky_replacement_stamp:
        raise ValueError('换天空源图在全尺寸解码之后变化')
    B.verify_source(value,spec.sky_replacement_path,shape)
    spec.sky_replacement_prepared = prepare(value,shape,cancelled=cancelled)
    if B.file_stamp(spec.sky_replacement_path) != before:
        spec.sky_replacement_prepared = None
        raise ValueError('准备全尺寸换天空时源图变化')


def attach_tile(pipe,spec,window):
    value = S.check(spec.sky_replacement)
    stage = SkyReplacementStage(pipe.device,(pipe.h,pipe.w))
    stage.set(value,spec.sky_replacement_prepared,window=window)
    pipe.sky_replacement = stage


def finish_export(spec):
    if not S.check(spec.sky_replacement)['enabled']:
        return
    if B.file_stamp(spec.sky_replacement_path) != tuple(spec.sky_replacement_stamp):
        raise ValueError('换天空导出期间源照片发生变化')
    prepared = spec.sky_replacement_prepared
    if prepared is None or B.file_stamp(spec.sky_replacement['asset']['path']) != prepared['asset_stamp']:
        raise ValueError('换天空导出期间素材发生变化')


def render_proxy(engine, render, *, allow_suspended=True):
    """Recoverable DISPLAY only. Strict stage/inspection/export never skip sky.

    A failed sky stage stays retained and suspended. Every omitted display must
    carry proxy_flags plus the persistent UI label; it cannot redeem a preview.
    """
    pipe=engine._vram; retained=pipe.sky_replacement
    engine._sky_previous_suspended=getattr(engine,'_sky_proxy_suspended',None)
    engine._sky_proxy_suspended=None
    try:
        return render()
    except Exception:
        if not allow_suspended or not retained.value['enabled'] or not retained.suspended:
            raise
    engine._sky_proxy_suspended=retained.suspended
    pipe.sky_replacement=SkyReplacementStage(pipe.device,(pipe.h,pipe.w))
    try:
        return render()
    finally:
        pipe.sky_replacement=retained


def proxy_flags(engine):
    reason=getattr(engine,'_sky_proxy_suspended',None)
    result={'sky_replacement_suspended':reason,
            'suspended_effects':[] if reason is None else [{'effect':'sky_replacement','reason':reason}],
            'display_quality':'proxy-incomplete' if reason else 'proxy'}
    if reason or getattr(engine,'_sky_previous_suspended',None):
        result['doc_state']=engine.doc_state()
    return result
