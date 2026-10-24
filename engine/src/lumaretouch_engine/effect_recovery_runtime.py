"""Source ownership, disposable Rust LMR2 masks, and export preparation."""
import json
from . import effect_recovery_state as S, local_mask_state as M
from . import facial_wrinkle_recovery as FACE
from .effect_recovery_stage import EffectRecoveryStage, check_fields


def availability(engine):
    pipe = engine._vram
    from .creative_derived_source import record
    derived = record(engine) is not None
    smoothing_error = None
    try:
        strength, _ = engine._retouch_render_args() if pipe is not None else (0, None)
    except Exception as error:
        if not derived:raise
        strength, smoothing_error = 0., str(error)
    from .fabric_controller import status
    fabric = status(engine)
    lip = getattr(pipe, 'lip_makeup_delta', None) if pipe else None
    lip_suspended = getattr(getattr(pipe, 'effect_recovery', None), 'suspended_targets', {}).get('lip_makeup') if pipe else None
    result = {
        'eye_bag_preserve': {'active':False,'reason':'眼袋 v2 恢复需要当前确切人物已应用的独立修正'},
        'eyeliner': {'active':False,'reason':'眼线恢复需要当前人物的已应用眼线图层'},
        'eyelash': {'active':False,'reason':'睫毛恢复需要当前人物的已应用睫毛图层'},
        'iris_makeup': {'active':False,'reason':'美瞳恢复需要当前人物已应用的美瞳图层'},
        'brow_makeup': {'active':False,'reason':'眉妆恢复需要当前人物的已应用眉妆图层'},
        'lipstick': {'active':False,'reason':'口红恢复需要当前人物的已应用口红图层'},
        'face_decoration': {'active':False,'reason':'面部装饰恢复只移除当前人物已应用的雀斑或痣贡献'},
        'blush_makeup': {'active':False,'reason':'腮红恢复需要当前人物的已应用腮红图层'},
        'eye_light': {'active':False,'reason':'眼神光恢复需要当前人物的已应用素材图层'},
        'facial_wrinkles': FACE.availability(pipe),
        'lip_makeup': {'active': bool(lip is not None and lip.any() and not lip_suspended),
                       'reason': lip_suspended or (None if lip is not None and bool(lip.any()) else '请先启用当前人物的唇妆增强')},
        'skin_smoothing': {'active': pipe is not None and strength != 0,
                           'reason': None if strength != 0 else '请先开启磨皮；只恢复本机现有磨皮/肌理算子'},
        'fabric_fine': {'active': bool(fabric['lit']), 'reason': fabric['reason'] or (None if fabric['lit'] else '请先开启衣物细褶')},
    }
    from .common_background_recovery import context as common_context
    try:
        common_context(engine, require_active=True)
        result['background_replace'] = {'active': True, 'reason': None}
    except Exception as error:
        result['background_replace'] = {'active': False, 'reason': str(error)}
    from .id_background_recovery import context as id_context
    try:
        id_context(engine,require_active=True)
        result['id_background']={'active':True,'reason':None}
    except Exception as error:
        result['id_background']={'active':False,'reason':str(error)}
    from . import people_recovery as PEOPLE
    if PEOPLE.managed(engine):
        result.update(PEOPLE.availability(engine))
    if derived:
        from .creative_derived_smoothing import recovery_context
        try:
            if smoothing_error is not None:raise ValueError(smoothing_error)
            context = recovery_context(engine)
            active = pipe is not None and context['recipe']['strength'] != 0
            result['skin_smoothing'] = {'active': active,
                'reason': None if active else '请先开启当前源的磨皮；只恢复本机现有磨皮/肌理算子'}
        except Exception as error:
            result['skin_smoothing'] = {'active': False, 'reason': str(error)}
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
    from .id_background_recovery import validate_state as validate_id
    validate_id(engine,requested)
    from .common_background_recovery import validate_state as validate_common
    validate_common(engine, requested)
    from .people_recovery import global_value
    value = global_value(engine, requested)
    from .eye_bag_effect_recovery import reject_global
    reject_global(value)
    row = engine._docs[engine._doc_index]
    before = M.file_stamp(row['path'])
    if row.get('_local_source_stamp') != before:
        raise ValueError('解码后源文件已变化，请重新打开照片')
    from . import creative_derived_source as D
    if D.record(engine) is not None:
        from . import creative_derived_global_recovery as G
        value = G.validate(value, D.binding(engine))
        fields = G.preview_fields(engine, value)
    else:
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
    from .id_background_recovery import enabled as id_enabled
    if id_enabled(value):
        # Other reviewed preview producers also call this owner directly. Bring
        # its ID dependency current only when needed; do not force model replay
        # on every status/proof read or reinstall unchanged checked fields.
        from .id_background_runtime import sync as sync_id
        sync_id(engine,strict=False)
    from .creative_derived_source import record, binding
    if record(engine) is not None:
        from .creative_derived_global_recovery import validate
        value = validate(value, binding(engine))
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
    from .creative_derived_source import record,binding
    effective = binding(engine) if record(engine) is not None else None
    if effective is not None and value['targets']:
        from .creative_derived_repair_runtime import verify_pipeline
        verify_pipeline(engine._vram, effective)
    from .id_background_recovery import enabled as id_enabled, context as id_context
    id_proof=id_context(engine) if id_enabled(value) else None
    from .common_background_recovery import enabled as common_enabled, context as common_context
    common_proof = common_context(engine) if common_enabled(value) else None
    return (json.dumps(common_proof,sort_keys=True),json.dumps(id_proof,sort_keys=True),json.dumps(value, sort_keys=True), M.file_stamp(row['path']) if source_stamp is None else source_stamp, id(engine._vram.src_f32), face_key,
            json.dumps(effective,sort_keys=True))


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
    from .eye_bag_effect_recovery import reject_global
    reject_global(S.check(snap.get('effect_recovery')))
    from .id_background_recovery import validate_state as validate_id
    validate_id(snap,snap.get('effect_recovery'))
    from .common_background_recovery import validate_state as validate_common
    validate_common(snap, snap.get('effect_recovery'))
    from .creative_derived_source import record
    if record(snap) is not None:
        from .creative_derived_global_recovery import verify_snapshot as verify_derived
        verify_derived(snap, path, shape)
        return
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
    from .eye_bag_effect_recovery import reject_global
    reject_global(value)
    if value['targets'] and not for_document:
        raise ValueError('恢复笔迹只能在其源照片导出，不能自动复制到其他照片')
    from .creative_derived_source import record
    if record(snap) is not None:
        from .creative_derived_global_recovery import verify_snapshot as verify_derived
        value = verify_derived(snap, snap.get('effect_recovery_path'), shape)
        from copy import deepcopy
        spec.creative_recovery_context = deepcopy(snap.get('creative_recovery_context'))
    spec.effect_recovery = value
    spec.effect_recovery_path = snap.get('effect_recovery_path')
    spec.effect_recovery_stamp = snap.get('effect_recovery_stamp')
    from .common_background_recovery import configure_export as configure_common
    configure_common(spec, snap)
    S.validate_budget(value, shape)
    if value['targets']:
        if not spec.effect_recovery_path:
            raise ValueError('全尺寸恢复导出缺少经过验证的源图路径')
        verify_snapshot(snap, spec.effect_recovery_path, shape)


def export_prepare(spec, shape, *, cancelled=lambda: False, source_pixels=None):
    value = S.check(spec.effect_recovery)
    if not value['targets']:
        spec.effect_recovery_fields = []
        return
    path = spec.effect_recovery_path
    before = M.file_stamp(path)
    if spec.effect_recovery_stamp is None or list(before) != spec.effect_recovery_stamp:
        raise ValueError('效果恢复源图自全尺寸解码后变化，停止导出')
    if getattr(spec, 'creative_base', None) is not None:
        from . import creative_derived_global_recovery as G, creative_derived_source as D
        source = D.binding({'creative_base': spec.creative_base})
        if tuple(shape) != (source['height'], source['width']):
            raise ValueError('Recovery export extent differs from immutable source')
        G.verify_context(spec.creative_recovery_context, source, value, path)
        G.verify_pixels(spec, source_pixels)
        spec.effect_recovery_fields = G.raster(value, source, shape, cancelled=cancelled)
    else:
        M.verify_source(value, path, shape)
        spec.effect_recovery_fields = raster_fields(value, path, shape, cancelled=cancelled)
    from .id_background_recovery import export_prepare as prepare_id
    prepare_id(spec)
    from .common_background_recovery import export_prepare as prepare_common
    prepare_common(spec)
    if M.file_stamp(path) != before:
        raise ValueError('生成全尺寸恢复蒙版时源图变化，停止导出')


def attach_tile(pipe, spec, window):
    from .id_background_recovery import verify_export as verify_id
    verify_id(spec)
    from .common_background_recovery import verify_export as verify_common
    verify_common(spec)
    y0, x0, y1, x1 = window
    check_fields(spec.effect_recovery_fields, state=spec.effect_recovery)
    fields = [{'target': item['target'], 'weight': item['weight'][y0:y1, x0:x1]}
              for item in spec.effect_recovery_fields]
    pipe.effect_recovery.set(fields, state=spec.effect_recovery)
