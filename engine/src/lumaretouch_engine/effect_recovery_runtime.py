"""Source ownership, disposable Rust LMR2 masks, and export preparation."""
import json
from . import effect_recovery_state as S, local_mask_state as M
from . import facial_wrinkle_recovery as FACE
from .effect_recovery_stage import EffectRecoveryStage, check_fields


def availability(engine):
    pipe = engine._vram
    strength, _ = engine._retouch_render_args() if pipe is not None else (0, None)
    from .fabric_controller import status
    fabric = status(engine)
    lip = getattr(pipe, 'lip_makeup_delta', None) if pipe else None
    lip_suspended = getattr(getattr(pipe, 'effect_recovery', None), 'suspended_targets', {}).get('lip_makeup') if pipe else None
    result = {
        'eyeliner': {'active':False,'reason':'眼线恢复需要当前人物的已应用眼线图层'},
        'lipstick': {'active':False,'reason':'口红恢复需要当前人物的已应用口红图层'},
        'blush_makeup': {'active':False,'reason':'腮红恢复需要当前人物的已应用腮红图层'},
        'eye_light': {'active':False,'reason':'眼神光恢复需要当前人物的已应用素材图层'},
        'facial_wrinkles': FACE.availability(pipe),
        'lip_makeup': {'active': bool(lip is not None and lip.any() and not lip_suspended),
                       'reason': lip_suspended or (None if lip is not None and bool(lip.any()) else '请先启用当前人物的唇妆增强')},
        'skin_smoothing': {'active': pipe is not None and strength != 0,
                           'reason': None if strength != 0 else '请先开启磨皮；只恢复本机现有磨皮/肌理算子'},
        'fabric_fine': {'active': bool(fabric['lit']), 'reason': fabric['reason'] or (None if fabric['lit'] else '请先开启衣物细褶')},
        'background_replace': {'active': bool(pipe and pipe.has_background()),
                               'reason': None if pipe and pipe.has_background() else '请先启用现有换底；不包含尚未实现的换天空或背景修复'},
    }
    from . import people_recovery as PEOPLE
    if PEOPLE.managed(engine):
        result.update(PEOPLE.availability(engine))
    return result


def raster_fields(value, path, shape, *, cancelled=lambda: False):
    value = S.check(value)
    S.validate_budget(value, shape)
    if value['source'] is not None:
        M.verify_source(value, path)
    fields = []
    for row in S.enabled(value):
        if cancelled():
            raise InterruptedError('效果恢复蒙版计算已取消')
        fields.append({'target': row['target'], 'weight': M.R.raster(row['recipe'], shape)})
    return check_fields(fields, shape, state=value)


def prepare_stage(engine, value):
    pipe = engine._vram
    if pipe is None:
        raise ValueError('没有可处理的照片')
    requested = S.check(value)
    from .people_recovery import global_value
    value = global_value(engine, requested)
    row = engine._docs[engine._doc_index]
    before = M.file_stamp(row['path'])
    if row.get('_local_source_stamp') != before:
        raise ValueError('解码后源文件已变化，请重新打开照片')
    M.verify_source(value, row['path'], (row['src_h'], row['src_w']))
    fields = raster_fields(value, row['path'], (pipe.h, pipe.w))
    if M.file_stamp(row['path']) != before:
        raise ValueError('生成恢复蒙版时源文件已变化')
    stage = EffectRecoveryStage(pipe.device, (pipe.h, pipe.w))
    stage.set(fields, state=value)
    FACE.suspend_only_target(stage, value, value["source"], engine._precompute)
    if M.file_stamp(row['path']) != before:
        raise ValueError('恢复蒙版装载到处理设备时源图变化')
    # The commit must use the stamp actually verified above, not read a newer
    # stamp after preparing old pixels and accidentally bless it as current.
    stage.verified_source_key = stage_key(engine, requested, source_stamp=before)
    return stage


def sync(engine, *, strict=False):
    pipe = engine._vram
    if pipe is None:
        return
    from .people_recovery import global_value
    value = global_value(engine)
    if not hasattr(pipe, 'effect_recovery'):
        pipe.effect_recovery = EffectRecoveryStage(pipe.device, (pipe.h, pipe.w))
    key = None
    try:
        key = stage_key(engine, value)
        if getattr(pipe, '_effect_recovery_key', None) == key:
            if strict and pipe.effect_recovery.suspended:
                raise ValueError(pipe.effect_recovery.suspended)
            return
        stage = prepare_stage(engine, value) if value['targets'] else EffectRecoveryStage(pipe.device, (pipe.h, pipe.w))
        pipe.effect_recovery, pipe._effect_recovery_key = stage, key
    except Exception as error:
        failed = EffectRecoveryStage(pipe.device, (pipe.h, pipe.w))
        failed.set([], state=value, reason=str(error))
        pipe.effect_recovery, pipe._effect_recovery_key = failed, key
        if strict:
            raise


def stage_key(engine, value, *, source_stamp=None):
    row = engine._docs[engine._doc_index]
    face_key = FACE.identity_key(engine._precompute) if any(r['target'] in FACE.FACE_TARGETS for r in value['targets']) else None
    return (json.dumps(value, sort_keys=True), M.file_stamp(row['path']) if source_stamp is None else source_stamp, id(engine._vram.src_f32), face_key)


def report(engine):
    from . import people_recovery as PEOPLE
    value = PEOPLE.value(engine)
    status = availability(engine)
    stage = getattr(engine._vram, 'effect_recovery', None)
    rows = {row['target']: row for row in value['targets']}
    suspended_targets = dict(getattr(stage, 'suspended_targets', {}))
    face_bytes = 0
    if PEOPLE.managed(engine):
        reason = getattr(engine._vram, 'people_suspended', None)
        if reason:
            suspended_targets.update({target: reason for target in FACE.FACE_TARGETS})
        prepared = getattr(engine._vram, 'people_prepared', None)
        if prepared is not None:
            face_bytes = sum(record['weight'].nbytes for record in prepared.recovery.values())
    return {'version': S.VERSION, 'targets': [{
        'target': name, 'label': S.LABELS[name], 'stage': S.STAGES[name],
        'active': status[name]['active'], 'reason': status[name]['reason'],
        'enabled': rows[name]['enabled'] if name in rows else True,
        'strokes': rows[name]['recipe']['objects'] if name in rows else [],
    } for name in S.TARGETS], 'suspended': getattr(stage, 'suspended', None),
        'suspended_targets': suspended_targets,
        'bytes_masks': (stage.resident_bytes() if stage else 0) + face_bytes,
        'boundaries': ['不恢复全部原图，也不擦掉曝光、曲线、LUT、局部调色或手工修补',
            '影棚背景祛瑕/祛穿帮/光影/断层使用背景调整工作区内的专属恢复；此处不混合其他算子',
            '尚未支持：独立人物瑕疵恢复、眼镜反光、碎发/白发、天空',
            '官方矩阵排除：祛油光、唇纹、双下巴、副乳；当前恢复笔不能用于这些效果',
            '恢复笔迹只属于当前源照片，不参与批量同步或预设',
            '面部祛纹、唇妆与眼神光恢复还绑定实际选中人物；重新检测不按人脸序号猜测身份']}


def verify_snapshot(snap, path, shape=None):
    value = S.check(snap.get('effect_recovery'))
    if not value['targets']:
        return
    before = M.file_stamp(path)
    M.verify_source(value, path, shape)
    FACE.verify(value, value["source"], snap.get("precompute"))
    if shape is not None:
        S.validate_budget(value, shape)
    if M.file_stamp(path) != before:
        raise ValueError('验证恢复配方时源文件发生变化')


def check_export_decode(snap, path, before, shape):
    value = S.check(snap.get('effect_recovery'))
    if not value['targets']:
        return
    if before is None or M.file_stamp(path) != before:
        raise ValueError('全尺寸解码过程中效果恢复源文件发生变化')
    verify_snapshot(snap, path, shape)
    if M.file_stamp(path) != before:
        raise ValueError('验证效果恢复源图后文件发生变化')
    snap['effect_recovery_path'], snap['effect_recovery_stamp'] = path, list(before)


def configure_export(spec, snap, shape, *, for_document):
    value = S.check(snap.get('effect_recovery'))
    if value['targets'] and not for_document:
        raise ValueError('恢复笔迹只能在其源照片导出，不能自动复制到其他照片')
    spec.effect_recovery = value
    spec.effect_recovery_path = snap.get('effect_recovery_path')
    spec.effect_recovery_stamp = snap.get('effect_recovery_stamp')
    S.validate_budget(value, shape)
    if value['targets']:
        if not spec.effect_recovery_path:
            raise ValueError('全尺寸恢复导出缺少经过验证的源图路径')
        verify_snapshot(snap, spec.effect_recovery_path, shape)


def export_prepare(spec, shape, *, cancelled=lambda: False):
    value = S.check(spec.effect_recovery)
    if not value['targets']:
        spec.effect_recovery_fields = []
        return
    path = spec.effect_recovery_path
    before = M.file_stamp(path)
    if spec.effect_recovery_stamp is None or list(before) != spec.effect_recovery_stamp:
        raise ValueError('效果恢复源图自全尺寸解码后变化，停止导出')
    M.verify_source(value, path, shape)
    spec.effect_recovery_fields = raster_fields(value, path, shape, cancelled=cancelled)
    if M.file_stamp(path) != before:
        raise ValueError('生成全尺寸恢复蒙版时源图变化，停止导出')


def attach_tile(pipe, spec, window):
    y0, x0, y1, x1 = window
    check_fields(spec.effect_recovery_fields, state=spec.effect_recovery)
    fields = [{'target': item['target'], 'weight': item['weight'][y0:y1, x0:x1]}
              for item in spec.effect_recovery_fields]
    pipe.effect_recovery.set(fields, state=spec.effect_recovery)
