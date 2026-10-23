"""Reviewed spill edits share the document history owner and ID compositor.

Receipt identity is retained, never blindly retried. A review token is consumed
before the first write, and failed writes restore both recipe and history ledger.
"""
from copy import deepcopy
from hashlib import sha256
import json

ACTIONS = frozenset(('id_spill_preview', 'id_spill_apply'))
EXTRA = {
    'id_spill_preview': {'parameters', 'coverage_ids', 'coverage_reviewed'},
    'id_spill_apply': {'token', 'reviewed', 'before_sha256', 'after_sha256'},
}
BASE = {'cmd', 'action', 'request_id', 'document_id', 'recipe_document_id', 'recipe_revision'}
MAX_RECEIPT_BYTES = 16 * 1024 * 1024
MAX_RESULT_BYTES = 4 * 1024 * 1024


def _bytes(value):
    return len(json.dumps(value, sort_keys=True, allow_nan=False, ensure_ascii=False).encode('utf-8'))


def envelope(request):
    action = request.get('action')
    if (action not in ACTIONS or request.get('cmd') != 'background'
            or set(request) != BASE | EXTRA[action]):
        raise ValueError('祛反光请求字段不完整或不兼容')
    rid = request.get('request_id')
    if type(rid) is not str or not 1 <= len(rid) <= 128:
        raise ValueError('祛反光请求身份无效')


class Controller:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.cache = {}

    def handle(self, request):
        from . import id_background_runtime as R, id_background_state as S
        from .spill_removal_review import owner
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
                if old != digest: raise ValueError('祛反光请求身份不能复用不同内容')
                result = deepcopy(cached); result['replayed'] = True; return
            if len(self.cache) >= 512:
                raise ValueError('祛反光回执容量已满，请保存并重启应用；未提交修改')
            reason = engine._guard_editable('background spill removal')
            if reason: raise ValueError(reason)
            if request['action'] == 'id_spill_preview':
                # Keep mutation receipts, but only one display pair. Old preview
                # identities remain explicit expired tombstones, not unknown
                # edits and not multi-gigabyte retained image histories.
                for old_id, (old_digest, old_result) in list(self.cache.items()):
                    if old_result.get('action') == 'id_spill_preview' and 'review' in old_result:
                        expired = {key: old_result[key] for key in (
                            'event', 'protocol', 'action', 'request_id', 'document_id')}
                        expired.update(success=False, outcome_unknown=False, requires_reload=False,
                                       error='旧祛反光预览已过期，请重新准备；没有提交图片修改')
                        self.cache[old_id] = (old_digest, expired)
                if sum(_bytes(item[1]) for item in self.cache.values()) + _bytes(R.report(engine)) + 3 * 1024 * 1024 > MAX_RECEIPT_BYTES:
                    raise ValueError('祛反光回执字节预算已满，请保存并重启应用；未提交修改')
                review = owner(engine).preview(request)
                result.update(success=True, review=review, report=R.report(engine))
                if _bytes(result) > MAX_RESULT_BYTES:
                    result.pop('review', None); result.pop('report', None)
                    raise ValueError('祛反光预览回执超过传输预算；未提交修改')
                return
            record = owner(engine).claim(request)
            prospective = R.report(engine)
            prospective['recipe'] = record['recipe']
            reserve = _bytes(prospective) + 65536
            if reserve > MAX_RESULT_BYTES:
                raise ValueError('祛反光审核配方超过单条回执预算；未提交修改')
            if sum(_bytes(item[1]) for item in self.cache.values()) + reserve > MAX_RECEIPT_BYTES:
                raise ValueError('祛反光回执字节预算已满，请保存并重启应用；未提交修改')
            before = engine._history_capture()
            if '_id_background' not in before:
                before = None
                raise ValueError('祛反光缺少统一历史状态；未提交修改')
            history = engine._history_controller()
            ledger = (list(history.undo), list(history.redo), history.group, history.group_ns)
            dirty = engine._project_dirty
            row = engine._docs[engine._doc_index]
            edit_time = row.get('_library_edit_time_ns')
            engine._fence_current_document()
            engine._cancel_snapshot('background spill removal')
            engine._id_background = S.check(record['recipe'])
            R.sync(engine, strict=True)
            verify(record['source'], engine)
            # Verify the actual installed state, not just the proposed recipe.
            # Advancing this transaction's revision is intentional; all other
            # complete source/people/recipe evidence remains identical.
            from .full_candidate_render import identity
            version = engine._document_versions().version(row)
            actual, _, _ = identity(engine, row, engine._capture_state(),
                                    version.document_id, str(version.revision))
            expected = {**record['proposed'], 'revision': str(version.revision)}
            if actual != expected:
                raise ValueError('祛反光安装后完整源图或编辑身份与已审核画面不一致')
            frame = engine._write_current_frame('id_spill_apply')
            actual, _, _ = identity(engine, row, engine._capture_state(),
                                    version.document_id, str(version.revision))
            if actual != expected:
                raise ValueError('祛反光出帧期间完整编辑或人物归属发生变化，已拒绝提交')
            engine._history_record('id_spill:' + rid, before, coalesce=False)
            if S.check(engine._history_capture()['_id_background']) != record['recipe']:
                raise ValueError('统一历史未保留已审核祛反光配方')
            frame['doc_state'] = engine.doc_state()
            result.update(success=True, report=R.report(engine), history=engine._history_report())
            if _bytes(result) > MAX_RESULT_BYTES:
                result.pop('report', None); result.pop('history', None)
                raise ValueError('祛反光最终回执超过传输预算，已拒绝提交')
            before = None
        except Exception as error:
            result['success'] = False; result['error'] = str(error)[:2000]
            if before is not None:
                try:
                    engine._history_apply(before)
                    if ledger is not None:
                        history.undo, history.redo, history.group, history.group_ns = ledger
                        engine._project_dirty = dirty
                        if edit_time is None: row.pop('_library_edit_time_ns', None)
                        else: row['_library_edit_time_ns'] = edit_time
                    R.sync(engine, strict=True)
                    frame = engine._write_current_frame('id_spill_rollback')
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
    value = engine.__dict__.get('_spill_removal_owner')
    if value is None: value = engine._spill_removal_owner = Controller(engine, emit)
    return value
