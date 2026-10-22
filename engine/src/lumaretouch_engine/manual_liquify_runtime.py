"""Source binding, final-stage lifecycle and full-resolution tiled export."""
import json
import numpy as np
from . import manual_liquify_state as S, local_mask_state as M
from .manual_liquify_field import replay
from .manual_liquify_stage import ManualLiquifyStage, check_field


def stage_key(engine, value):
    row = engine._docs[engine._doc_index]
    return (json.dumps(value, sort_keys=True), M.file_stamp(row['path']), id(engine._vram.src_f32))


def verified_value(engine, value):
    value = S.check(value)
    row = engine._docs[engine._doc_index]
    before = M.file_stamp(row['path'])
    if row.get('_local_source_stamp') != before:
        raise ValueError('源图自解码后变化，请重新打开照片')
    M.verify_source(value, row['path'], (row['src_h'], row['src_w']))
    if M.file_stamp(row['path']) != before:
        raise ValueError('液化源图身份验证时文件发生变化')
    return value


def prepare_stage(engine, value, *, field=None, supplied=False):
    value = verified_value(engine, value)
    pipe = engine._vram
    if not supplied:
        field = replay(value, (pipe.h, pipe.w))
    stage = ManualLiquifyStage(pipe.device, (pipe.h, pipe.w), pipe.high_precision_warp)
    stage.set(field, required=bool(value['strokes']))
    return stage


def sync(engine, *, strict=False):
    pipe = engine._vram
    if pipe is None: return
    value = S.check(getattr(engine, '_manual_liquify', None))
    key = None
    try:
        key = stage_key(engine, value)
        if getattr(pipe, '_manual_liquify_key', None) == key:
            if strict and pipe.manual_liquify.suspended:
                raise ValueError(pipe.manual_liquify.suspended)
            return
        stage = prepare_stage(engine, value) if value['strokes'] else ManualLiquifyStage(pipe.device, (pipe.h, pipe.w), pipe.high_precision_warp)
        pipe.manual_liquify, pipe._manual_liquify_key = stage, key
    except Exception as error:
        stage = ManualLiquifyStage(pipe.device, (pipe.h, pipe.w), pipe.high_precision_warp)
        stage.set(None, reason=str(error))
        pipe.manual_liquify, pipe._manual_liquify_key = stage, key
        if strict: raise


def report(engine):
    value = S.check(getattr(engine, '_manual_liquify', None))
    stage = getattr(engine._vram, 'manual_liquify', None)
    return {'version': S.VERSION, 'domain': S.DOMAIN, 'strokes': value['strokes'],
            'suspended': getattr(stage, 'suspended', None), 'bytes_field': stage.resident_bytes() if stage else 0,
            'boundaries': ['在全部效果与背景合成之后、裁剪旋转之前塑形；重建只恢复手动液化',
                           '冻结保留当前位置的手动形变，解冻取消保护；红色表示保护强度',
                           '笔迹只属于这张源照片，不跟踪人物，也不进入批量同步或预设']}


def verify_snapshot(snap, path, shape=None):
    value = S.check(snap.get('manual_liquify'))
    if not value['strokes']: return
    before = M.file_stamp(path)
    M.verify_source(value, path, shape)
    if shape is not None: S.validate_budget(value, shape)
    if M.file_stamp(path) != before: raise ValueError('验证液化源图时文件变化')


def check_export_decode(snap, path, before, shape):
    value = S.check(snap.get('manual_liquify'))
    if not value['strokes']: return
    if before is None or M.file_stamp(path) != before:
        raise ValueError('全尺寸液化源图在解码时发生变化')
    verify_snapshot(snap, path, shape)
    if M.file_stamp(path) != before: raise ValueError('液化源图在身份验证时发生变化')
    snap['manual_liquify_path'], snap['manual_liquify_stamp'] = path, list(before)


def configure_export(spec, snap, shape, *, for_document):
    value = S.check(snap.get('manual_liquify'))
    if value['strokes'] and not for_document:
        raise ValueError('手动液化仅在其原照片重放，不允许自动复制到另一张照片')
    spec.manual_liquify = value
    spec.manual_liquify_path = snap.get('manual_liquify_path')
    spec.manual_liquify_stamp = snap.get('manual_liquify_stamp')
    S.validate_budget(value, shape)
    if value['strokes']:
        if not spec.manual_liquify_path: raise ValueError('全尺寸液化缺少已验证的源照片')
        verify_snapshot(snap, spec.manual_liquify_path, shape)


def export_prepare(spec, shape, *, cancelled=lambda: False):
    value = S.check(spec.manual_liquify)
    spec.manual_liquify_field = None
    if not value['strokes']: return 0.
    path = spec.manual_liquify_path
    before = M.file_stamp(path)
    if spec.manual_liquify_stamp is None or list(before) != spec.manual_liquify_stamp:
        raise ValueError('液化源图自全尺寸解码后发生变化')
    M.verify_source(value, path, shape)
    spec.manual_liquify_field = replay(value, shape, cancelled=cancelled)
    if M.file_stamp(path) != before: raise ValueError('液化场重放过程中源图发生变化')
    field = check_field(spec.manual_liquify_field, shape)
    # L-infinity support: each x/y source footprint fits this conservative halo.
    return float(np.max(np.abs(field[..., :2])))


def attach_tile(pipe, spec, window):
    value = S.check(spec.manual_liquify)
    field = spec.manual_liquify_field
    if value['strokes'] and field is None: raise ValueError('全尺寸液化场缺失，停止出片')
    y0, x0, y1, x1 = window
    pipe.manual_liquify.set(None if field is None else field[y0:y1, x0:x1], required=bool(value['strokes']))
