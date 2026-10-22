# SPDX-License-Identifier: GPL-3.0-or-later
"""Trusted capture port. Full render output only; never accept renderer-supplied pixels.

Call capture_current on the engine command thread under its existing edit exclusion.
The returned callback must be checked again immediately before catalogue commit.
"""
from dataclasses import dataclass
from typing import Callable
from copy import deepcopy
from pathlib import Path
from . import sample_library_state as S


@dataclass(frozen=True)
class FrozenCapture:
    frame: object
    width: int
    height: int
    verify_current: Callable[[], None]
    origin: str = 'engine-export-float-scale-1-v1'


def validate_capture(capture):
    from .reference_color_review import validate
    if type(capture) is not FrozenCapture or capture.origin != 'engine-export-float-scale-1-v1':
        S.fail('只能使用引擎冻结的原分辨率完整渲染，不能导入截图作为当前结果')
    rgb = validate(capture.frame)
    if rgb.shape[:2] != (capture.height, capture.width) or capture.width * capture.height > S.MAX_PIXELS:
        S.fail('冻结结果尺寸超出完整参考预算')
    if capture.frame.rgb.flags.writeable or capture.frame.authentic_mask.flags.writeable:
        S.fail('当前结果尚未冻结为独立只读画布')
    if not callable(capture.verify_current): S.fail('当前结果缺少文档版本守卫')
    return capture


def heavy_reason(engine):
    """Do not overlap known heavy owners or silently cancel the user's work."""
    for name in ('bench', '_export'):
        owner = getattr(engine, name, None)
        if owner is not None and owner.is_alive(): return '有导出或性能任务正在进行，请结束后再处理完整样片'
    inspection = engine.__dict__.get('_inspection')
    if inspection is not None and inspection.worker_running:
        return '全尺寸检查仍占用渲染资源，请等检查结束后再处理完整样片'
    for name in ('_manual_liquify_preview_owner', '_sky_replacement_preview_owner', '_studio_background_preview_owner'):
        owner = engine.__dict__.get(name)
        if owner is not None and (owner.job is not None or owner.latest is not None):
            return '效果预览正在计算，请等预览结束后再处理完整样片'
    for name in ('_prompted_mask_owner', '_sky_semantic_owner'):
        owner = engine.__dict__.get(name)
        job = getattr(owner, 'job', None)
        if job is not None and job.state == 'running': return '自动选区正在计算，请等选区结束后再处理完整样片'
    return None


def capture_reason(engine):
    reason = engine._guard_editable('创建样片') or heavy_reason(engine)
    if reason: return reason
    for name in ('_manual_liquify_preview_owner', '_sky_replacement_preview_owner', '_studio_background_preview_owner',
                 '_optics_preview_owner', '_effect_recovery_preview_owner', '_local_grade_live_owner'):
        owner = engine.__dict__.get(name)
        if getattr(owner, 'session', None) is not None:
            return '请先提交或取消未确认的效果预览；样片只冻结已提交编辑的完整成片'
    return None


def context(engine):
    if not engine._image_loaded or not 0 <= engine._doc_index < len(engine._docs):
        return {'available': False, 'document_id': '', 'load_id': '', 'revision': '0', 'label': '未打开照片', 'key': ''}
    reason = capture_reason(engine)
    row = engine._docs[engine._doc_index]
    version = engine._document_versions().version(row)
    return {'available': not bool(reason), 'unavailableReason': reason or '',
            'document_id': version.document_id, 'load_id': str(engine._load_id), 'revision': str(version.revision),
            'label': Path(row['path']).name,
            'key': version.document_id + ':' + str(version.revision) + ':' + str(engine._load_id)}


def capture_current(engine, expected_context, cancelled=lambda: False):
    """Reuse actual original decode/export/provenance owner, not proxy reconstruction."""
    import numpy as np
    from .sample_library_images import cancelled as check_cancel
    from .reference_color_engine import render
    from .reference_color_review import ColorInput
    from .optics_candidate_identity import fingerprint
    from .render_snapshot import own_render_inputs
    from . import local_mask_state as M
    check_cancel(cancelled)
    reason = capture_reason(engine)
    if reason: S.fail(reason, 'capture_unavailable')
    index = engine._doc_index
    if not engine._image_loaded or not 0 <= index < len(engine._docs):
        S.fail('请先打开需要保存效果的照片', 'capture_unavailable')
    row = engine._docs[index]
    versions = engine._document_versions(); version = versions.version(row)
    document_id = version.document_id; revision = str(version.revision)
    if (type(expected_context) is not dict or set(expected_context) != {'document_id', 'revision'}
            or expected_context != {'document_id': document_id, 'revision': revision}):
        S.fail('当前照片与创建样片请求已不一致，请刷新后重试', 'stale_document')
    # This copies under command-thread exclusion. The renderer never swaps live
    # editor state or borrows another document's face/colour/replacement state.
    state = own_render_inputs(engine._capture_state(), max_asset_bytes=512 * 1024 * 1024).value
    key = fingerprint(state); stamp = M.file_stamp(row['path'])
    try:
        frame = render(engine, row, state, document_id, revision, reference=True, cancelled=cancelled)
    except Exception as error:
        check_cancel(cancelled)  # Cancellation before any catalogue write is known not applied.
        if isinstance(error, S.LibraryError): raise
        raise S.LibraryError(str(error)[:1000], code='capture_unavailable') from error
    check_cancel(cancelled)
    # Detach outputs from the export spec/temporary owner as well as live state.
    rgb = np.array(frame.rgb, dtype=np.float32, order='C', copy=True)
    mask = np.array(frame.authentic_mask, dtype=np.bool_, order='C', copy=True)
    rgb.setflags(write=False); mask.setflags(write=False)
    frozen = ColorInput(frame.document_id, frame.revision, deepcopy(frame.source), frame.state_key, rgb, mask)

    def verify():
        check_cancel(cancelled)
        if (engine._doc_index != index or index >= len(engine._docs) or engine._docs[index] is not row
                or not engine._image_loaded or str(versions.version(row).revision) != revision
                or fingerprint(engine._capture_state()) != key or M.file_stamp(row['path']) != stamp
                or M.source_digest(row['path']) != frozen.source['sha256']):
            S.fail('照片、编辑版本或源文件已变化，请重新创建样片', 'stale_document')
    verify()
    return validate_capture(FrozenCapture(frozen, int(rgb.shape[1]), int(rgb.shape[0]), verify))
