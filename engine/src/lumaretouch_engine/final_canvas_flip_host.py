"""Document/revision-bound desired state, retained exact receipts, one transaction."""
from copy import deepcopy
from . import final_canvas_flip_state as S
from .final_canvas_flip_recovery import mark, outcome


def report(engine):
    from .extended_tone_host import revision
    from .final_canvas_output import available
    recipe = S.check(getattr(engine, S.KEY, S.neutral()))
    return {'operation_id': S.OP, **recipe, 'active': S.active(recipe),
            'available': available(), 'document_id': str(engine._load_id),
            'revision': str(revision(engine)), 'coordinate_capture_available': not S.active(recipe),
            'reason': S.REASON if S.active(recipe) else None}


def _commit(engine, request, emit):
    from .extended_tone_host import revision
    from .optics_candidate_identity import fingerprint
    mark(engine, 'no_write')
    if set(request) != {'cmd', 'request_id', 'document_id', 'revision', 'horizontal', 'vertical'} or request['cmd'] != 'final_canvas_flip':
        raise ValueError('Final canvas flip requires exact request/document/revision and desired booleans')
    recipe = S.check({key: request[key] for key in ('horizontal', 'vertical')})
    document, rev = str(engine._load_id), revision(engine)
    if type(request['document_id']) is not str or type(request['revision']) is not str or (request['document_id'], request['revision']) != (document, str(rev)):
        raise ValueError('翻转请求的照片或版本已变化；未修改，请刷新当前照片')
    reason = engine._guard_editable('final canvas flip')
    if reason: raise ValueError(reason)
    if engine.__dict__.get('_final_canvas_flip_reload') == document:
        raise ValueError('翻转回滚未确认；请重新载入此照片')
    if S.active(recipe):
        from .final_canvas_output import native
        native()
    previous = S.check(getattr(engine, S.KEY, S.neutral()))
    if recipe == previous:
        return {'phase': 'no_change', 'spec': recipe, 'result_revision': str(rev)}
    engine._cancel_snapshot('final_canvas_flip')
    engine._close_owned_previews()
    before = engine._history_capture()
    history = engine._history_controller()
    ledger = (list(history.undo), list(history.redo), history.group, history.group_ns)
    before_proof = fingerprint((before, ledger))
    dirty = engine._project_dirty
    rows, index = getattr(engine, '_docs', ()), getattr(engine, '_doc_index', -1)
    row = rows[index] if 0 <= index < len(rows) else None
    edit_time = (row is not None and '_library_edit_time_ns' in row,
                 None if row is None else row.get('_library_edit_time_ns'))
    mark(engine, 'unknown')
    try:
        setattr(engine, S.KEY, recipe)
        engine._vram.final_canvas_flip = recipe
        frame = engine._write_current_frame('final_canvas_flip')
        engine._history_record('final_canvas_flip', before, coalesce=False)
        limit = getattr(history, 'limit', 64)
        if (len(history.undo) != min(len(ledger[0]) + 1, limit) or not history.undo
                or history.redo or history.group != 'final_canvas_flip'
                or S.from_state(history.undo[-1]) != previous):
            raise RuntimeError('翻转未记录准确的离散历史步骤')
        engine._fence_current_document()
        if str(engine._load_id) != document or revision(engine) != rev + 1 or S.from_state(engine._history_capture()) != recipe:
            raise RuntimeError('翻转提交后的照片/版本/配方证明不匹配')
    except Exception as error:
        try:
            setattr(engine, S.KEY, previous)
            engine._vram.final_canvas_flip = previous
            history.undo, history.redo, history.group, history.group_ns = ledger
            engine._project_dirty = dirty
            if row is not None:
                if edit_time[0]: row['_library_edit_time_ns'] = edit_time[1]
                else: row.pop('_library_edit_time_ns', None)
            rollback_frame = engine._write_current_frame('final_canvas_flip_rollback')
            restored = (engine._history_capture(), (list(history.undo), list(history.redo), history.group, history.group_ns))
            if (fingerprint(restored) != before_proof or str(engine._load_id) != document
                    or revision(engine) != rev or engine._project_dirty != dirty
                    or S.check(engine._vram.final_canvas_flip) != previous):
                raise RuntimeError('状态/历史/版本/管线回滚证明不匹配')
        except Exception as rollback_error:
            engine._final_canvas_flip_reload = document
            failure = RuntimeError(f'翻转失败 ({error})；回滚未确认 ({rollback_error})；需要重新载入')
            failure.outcome_unknown = True
            raise failure from error
        mark(engine, 'rolled_back')
        # Frame delivery does not change the proved recipe/history transaction.
        try: emit(rollback_frame)
        except Exception: pass
        failure = RuntimeError(f'翻转未提交，已完整回滚：{error}')
        failure.rolled_back = True
        raise failure from error
    mark(engine, 'applied')
    proof = {'phase': 'applied', 'spec': recipe, 'result_revision': str(rev + 1)}
    try:
        frame['doc_state'] = engine.doc_state()
        emit(frame)
        engine.emit_session_state()
    except Exception:
        proof['frame_delivery_unknown'] = True
    return proof


def _packet(request):
    return {'event': 'final_canvas_flip_result', 'protocol': 1,
            'request_id': request.get('request_id'), 'original_request': deepcopy(request),
            'success': False, 'outcome_unknown': False, 'requires_reload': False,
            'phase': 'rejected'}


def command(engine, request, emit):
    mark(engine, 'no_write')
    if type(request) is not dict: raise ValueError('翻转请求必须是对象')
    rid = request.get('request_id')
    if type(rid) is not str or not 1 <= len(rid) <= 128: raise ValueError('翻转请求缺少有界身份')
    receipts = engine.__dict__.setdefault('_final_canvas_flip_receipts', {})
    if rid in receipts:
        original, packet = receipts[rid]
        if original != request: raise ValueError('翻转请求身份已用于不同内容；未发送')
        emit(deepcopy(packet))
        return deepcopy(packet)
    if len(receipts) >= 4096: raise ValueError('翻转回执已满；请保存并重启应用')
    packet = _packet(request)
    try:
        packet.update(_commit(engine, request, emit), success=True)
    except Exception as error:
        unknown = bool(getattr(error, 'outcome_unknown', False))
        packet.update(error=str(error)[:2000], outcome_unknown=unknown, requires_reload=unknown,
                      phase='unknown' if unknown else 'rolled_back' if getattr(error, 'rolled_back', False) else 'rejected')
    receipts[rid] = (deepcopy(request), deepcopy(packet))
    emit(deepcopy(packet))
    return packet


def dispatch_rejected(engine, request, error, started, emit):
    """Correlate failures in dispatcher guards, before the owner was entered."""
    retained = engine.__dict__.get('_final_canvas_flip_receipts', {}).get(request.get('request_id'))
    if retained is not None and retained[0] == request:
        emit(deepcopy(retained[1]))
        return
    packet = _packet(request)
    # A handler crash without a retained proof is conservatively unknown.
    unknown = bool(started) and outcome(engine) not in ('no_write', 'rolled_back')
    packet.update(error=str(error)[:2000], outcome_unknown=unknown,
                  requires_reload=unknown, phase='unknown' if unknown else 'rejected')
    emit(packet)
