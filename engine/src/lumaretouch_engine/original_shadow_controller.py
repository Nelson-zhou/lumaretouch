"""Reviewed original-shadow edits share ID rendering and unified history.

Tokens are consumed before writes. Terminal receipts are retained, while only
one display pair survives. Failed commits restore both recipe and history.
"""
from copy import deepcopy
from hashlib import sha256
import json

ACTIONS = frozenset(('id_original_shadow_preview', 'id_original_shadow_apply', 'id_original_shadow_paint_source'))
EXTRA = {
    'id_original_shadow_preview': {'parameters', 'lit_ids', 'retention_ids',
                                   'samples_reviewed', 'uniform_floor_confirmed'},
    'id_original_shadow_apply': {'token', 'reviewed', 'before_sha256', 'after_sha256'},
    'id_original_shadow_paint_source': set(),
}
BASE = {'cmd', 'action', 'request_id', 'document_id', 'recipe_document_id', 'recipe_revision'}
MAX_RECEIPT_BYTES = 16 * 1024 * 1024
MAX_RESULT_BYTES = 4 * 1024 * 1024


def _bytes(value):
    return len(json.dumps(value, sort_keys=True, allow_nan=False, ensure_ascii=False).encode('utf-8'))


def envelope(request):
    action = request.get('action')
    optional = {'paint', 'clear_samples'} if action == 'id_original_shadow_preview' else set()
    if (action not in ACTIONS or request.get('cmd') != 'background'
            or not BASE | EXTRA[action] <= set(request)
            or set(request) - (BASE | EXTRA[action] | optional)):
        raise ValueError('原阴影请求字段不完整或不兼容')
    if 'clear_samples' in request and request['clear_samples'] is not True:
        raise ValueError('清除原阴影样本字段只能省略或明确为 true')
    if _bytes(request) > 65536:
        raise ValueError('原阴影请求超过 64 KiB；请减少单次所选对象数量')
    rid = request.get('request_id')
    if type(rid) is not str or not 1 <= len(rid) <= 128:
        raise ValueError('原阴影请求身份无效')


class Controller:
    def __init__(self, engine, emit):
        self.engine, self.emit, self.cache = engine, emit, {}

    def handle(self, request):
        from . import id_background_runtime as R, id_background_state as S
        from .original_shadow_review import owner
        from .creative_derived_source import verify
        engine = self.engine; rid = request.get('request_id')
        result = {'event': 'id_background_result', 'protocol': 1,
                  'action': request.get('action'), 'request_id': rid,
                  'document_id': request.get('document_id'), 'success': False,
                  'outcome_unknown': False, 'requires_reload': False}
        digest = None; before = None; ledger = None; frame = None
        try:
            envelope(request)
            digest = sha256(json.dumps(request, sort_keys=True, allow_nan=False).encode()).hexdigest()
            if rid in self.cache:
                old, cached = self.cache[rid]
                if old != digest: raise ValueError('原阴影请求身份不能复用不同内容')
                result = deepcopy(cached); result['replayed'] = True; return
            if len(self.cache) >= 512:
                raise ValueError('原阴影回执容量已满，请保存并重启应用；未提交修改')
            reason = engine._guard_editable('background original shadow')
            if reason: raise ValueError(reason)
            if request['action'] == 'id_original_shadow_paint_source':
                from .original_shadow_paint_source import owner as paint_owner
                paint_owner(engine).record = None
                owner(engine).review = None
                for old_id, (old_digest, old_result) in list(self.cache.items()):
                    if 'shadow_paint_source' in old_result or 'shadow_review' in old_result:
                        expired = {key: old_result[key] for key in (
                            'event', 'protocol', 'action', 'request_id', 'document_id')}
                        expired.update(success=False, outcome_unknown=False, requires_reload=False,
                                       error='旧原阴影画布或预览已过期；没有提交图片修改')
                        self.cache[old_id] = (old_digest, expired)
                if sum(_bytes(item[1]) for item in self.cache.values()) + MAX_RESULT_BYTES > MAX_RECEIPT_BYTES:
                    raise ValueError('原阴影画布回执预算已满；未提交修改')
                public = paint_owner(engine).prepare(request)
                result.update(success=True, report=R.report(engine), shadow_paint_source=public)
                if _bytes(result) > MAX_RESULT_BYTES:
                    result.pop('shadow_paint_source', None); result.pop('report', None)
                    paint_owner(engine).record = None
                    raise ValueError('原阴影画布三张显示图超过总传输预算；未提交修改')
                return
            if request['action'] == 'id_original_shadow_preview':
                owner(engine).review = None
                for old_id, (old_digest, old_result) in list(self.cache.items()):
                    if old_result.get('action') == request['action'] and 'shadow_review' in old_result:
                        expired = {key: old_result[key] for key in (
                            'event', 'protocol', 'action', 'request_id', 'document_id')}
                        expired.update(success=False, outcome_unknown=False, requires_reload=False,
                                       error='旧原阴影预览已过期，请重新准备；没有提交图片修改')
                        self.cache[old_id] = (old_digest, expired)
                if sum(_bytes(item[1]) for item in self.cache.values()) + _bytes(R.report(engine)) + 3 * 1024 * 1024 > MAX_RECEIPT_BYTES:
                    raise ValueError('原阴影回执字节预算已满，请保存并重启应用；未提交修改')
                public = owner(engine).preview(request)
                result.update(success=True, report=R.report(engine), shadow_review=public)
                if _bytes(result) > MAX_RESULT_BYTES:
                    result.pop('shadow_review', None); result.pop('report', None)
                    owner(engine).review = None
                    raise ValueError('原阴影预览回执超过传输预算；未提交修改')
                return
            record = owner(engine).claim(request)
            prospective = R.report(engine)
            prospective['recipe'] = record['recipe']
            reserve = _bytes(prospective) + 65536
            if reserve > MAX_RESULT_BYTES:
                raise ValueError('原阴影审核配方超过单条回执预算；未提交修改')
            if sum(_bytes(item[1]) for item in self.cache.values()) + reserve > MAX_RECEIPT_BYTES:
                raise ValueError('原阴影回执字节预算已满，请保存并重启应用；未提交修改')
            before = engine._history_capture()
            if '_id_background' not in before:
                before = None
                raise ValueError('原阴影缺少统一历史状态；未提交修改')
            history = engine._history_controller()
            ledger = (list(history.undo), list(history.redo), history.group, history.group_ns)
            dirty = engine._project_dirty
            row = engine._docs[engine._doc_index]
            edit_time = row.get('_library_edit_time_ns')
            engine._fence_current_document()
            engine._cancel_snapshot('background original shadow')
            engine._id_background = S.check(record['recipe'])
            R.sync(engine, strict=True)
            verify(record['source'], engine)
            from .full_candidate_render import identity
            version = engine._document_versions().version(row)
            expected = {**record['proposed'], 'revision': str(version.revision)}
            actual, _, _ = identity(engine, row, engine._capture_state(),
                                    version.document_id, str(version.revision))
            if actual != expected:
                raise ValueError('原阴影安装后完整源图或编辑身份与已审核画面不一致')
            frame = engine._write_current_frame('id_original_shadow_apply')
            actual, _, _ = identity(engine, row, engine._capture_state(),
                                    version.document_id, str(version.revision))
            if actual != expected:
                raise ValueError('原阴影出帧期间完整编辑或人物归属发生变化，已拒绝提交')
            engine._history_record('id_original_shadow:' + rid, before, coalesce=False)
            if S.check(engine._history_capture()['_id_background']) != record['recipe']:
                raise ValueError('统一历史未保留已审核原阴影配方')
            frame['doc_state'] = engine.doc_state()
            result.update(success=True, report=R.report(engine), history=engine._history_report())
            if _bytes(result) > MAX_RESULT_BYTES:
                result.pop('report', None); result.pop('history', None)
                raise ValueError('原阴影最终回执超过传输预算，已拒绝提交')
            before = None
        except Exception as error:
            result['success'] = False; result['error'] = str(error)[:2000]
            if request.get('action') == 'id_original_shadow_paint_source':
                from .original_shadow_paint_source import owner as paint_owner
                paint_owner(engine).record = None
                result.pop('shadow_paint_source', None)
            if before is not None:
                try:
                    engine._history_apply(before)
                    if ledger is not None:
                        history.undo, history.redo, history.group, history.group_ns = ledger
                        engine._project_dirty = dirty
                        if edit_time is None: row.pop('_library_edit_time_ns', None)
                        else: row['_library_edit_time_ns'] = edit_time
                    R.sync(engine, strict=True)
                    # Restoration must match the frozen BEFORE proof, not a
                    # newly observed identity that could bless changed people,
                    # source pixels, or partially restored upstream edits.
                    from .full_candidate_render import identity
                    if (engine._load_id != record['document_id']
                            or engine._docs[engine._doc_index] is not row):
                        raise ValueError('原阴影回滚期间照片已切换')
                    verify(record['source'], engine)
                    restored = engine._document_versions().version(row)
                    expected = {**record['prior'], 'revision': str(restored.revision)}
                    actual, _, _ = identity(engine, row, engine._capture_state(),
                                            restored.document_id, str(restored.revision))
                    if actual != expected:
                        raise ValueError('原阴影回滚未恢复已冻结的完整编辑与人物归属')
                    frame = engine._write_current_frame('id_original_shadow_rollback')
                    actual, _, _ = identity(engine, row, engine._capture_state(),
                                            restored.document_id, str(restored.revision))
                    if actual != expected:
                        raise ValueError('原阴影回滚出帧改变了已冻结的完整状态')
                    frame['doc_state'] = engine.doc_state(); self.emit(frame)
                except Exception:
                    result.update(outcome_unknown=True, requires_reload=True)
                    engine._vram = None
        finally:
            if result['success'] and frame is not None:
                try: self.emit(frame)
                except Exception: result['frame_delivery_unknown'] = True
            if rid and digest and rid not in self.cache and len(self.cache) < 512:
                self.cache[rid] = (digest, deepcopy(result))
            self.emit(result)


def controller(engine, emit):
    value = engine.__dict__.get('_original_shadow_owner')
    if value is None: value = engine._original_shadow_owner = Controller(engine, emit)
    return value
