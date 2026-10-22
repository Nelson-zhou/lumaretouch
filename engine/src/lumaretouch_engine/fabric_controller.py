"""Small engine adapter for fabric recipe, availability and transactional edits."""
from .optional_dependencies import optional_module
from .fabric_stage import FabricStage, check_amount, clothing_mask, face_scale, measure_field


def status(engine):
    import numpy as np
    mask = clothing_mask(engine._precompute)
    dependency = optional_module('cv2') is not None
    available = dependency and mask is not None and bool(np.any(np.asarray(mask) > 1e-3))
    stage = getattr(engine._vram, 'fabric', None)
    amount = getattr(engine, '_fabric_amount', 0.0)
    return {'amount': amount, 'available': available,
            'lit': bool(available and amount and stage is not None and stage.field is not None),
            'scope': 'all_clothes',
            'reason': None if available else '当前运行环境缺少 OpenCV，衣物细褶不可用' if not dependency else '衣物语义蒙版不可用，请先完成人像分析；不会用皮肤反选或人物轮廓代替'}


def sync(engine):
    """Called before rendering: repairs, proxy switches and undo invalidate by identity."""
    pipe = engine._vram
    if pipe is None:
        return
    if not hasattr(pipe, 'fabric'):
        pipe.fabric = FabricStage(pipe.device)
    stage = pipe.fabric
    amount = check_amount(getattr(engine, '_fabric_amount', 0.0))
    mask = clothing_mask(engine._precompute)
    if amount == 0 or not status(engine)['available']:
        stage.clear()
        return
    source = pipe.base()
    key = (id(source), pipe.repair_version, id(mask), source.shape[-2:], face_scale(engine._precompute, pipe.h, pipe.w))
    if stage.key != key:
        pixels = source[0].permute(1, 2, 0).detach().cpu().numpy()
        stage.install(measure_field(pixels, mask, key[-1]), amount)
        stage.key = key
    stage.amount = amount


def handle(engine, p, emit):
    previous = getattr(engine, '_fabric_amount', 0.0)
    try:
        why = engine._guard_editable('fabric')
        if why:
            raise ValueError(why)
        if set(p) - {'cmd', 'action', 'amount', 'document_id'}:
            raise ValueError('衣物细褶收到未知字段')
        if not p.get('document_id') or p['document_id'] != engine._load_id:
            raise ValueError('图片已切换，请在当前图片重试')
        if p.get('action', 'set') not in ('set', 'clear'):
            raise ValueError('衣物细褶动作无效')
        amount = check_amount(0.0 if p.get('action') == 'clear' else p.get('amount'))
        if amount and not status(engine)['available']:
            raise ValueError(status(engine)['reason'])
        engine._fabric_amount = amount
        frame = engine._write_current_frame('fabric')
        frame['doc_state'] = engine.doc_state()
        emit(frame)
        emit({'event': 'fabric_done', 'fabric': status(engine), 'document_id': engine._load_id})
    except Exception as error:
        engine._fabric_amount = previous
        try:
            sync(engine)
        except Exception:
            if engine._vram is not None and hasattr(engine._vram, 'fabric'):
                engine._vram.fabric.clear()
        emit({'event': 'error', 'error': f'衣物细褶未提交：{error}'})
        engine.emit_session_state()
