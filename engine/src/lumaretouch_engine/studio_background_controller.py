"""One rendered final gesture, one history transaction, one terminal receipt."""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json
from . import studio_background_state as S, studio_background_runtime as R
from .studio_background_preview import controller as preview_controller, ident
from .white_balance_controller import identity, error_text
KEYS = {'cmd', 'action', 'request_id', 'preview_id', 'session_id', 'document_id'}


class StudioBackgroundController:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.pending = None
        self.cache = OrderedDict()

    def prepare(self, p):
        result = {'event': 'studio_background_result', 'protocol': 1, 'action': 'apply',
                  **{k: identity(p.get(k), 128) for k in ('request_id', 'preview_id', 'session_id', 'document_id')},
                  'success': False, 'outcome_unknown': False, 'requires_reload': False}
        self.pending = {'result': result, 'digest': None, 'started': False}
        try:
            if set(p) != KEYS or p['cmd'] != 'studio_background' or p['action'] != 'apply': raise ValueError('背景调整提交字段无效')
            ident(p['preview_id']); ident(p['session_id'])
            if result['request_id'] is None: raise ValueError('背景调整请求身份无效')
            digest = self.pending['digest'] = sha256(json.dumps(p, sort_keys=True, allow_nan=False).encode()).hexdigest()
            if result['request_id'] in self.cache:
                old, receipt = self.cache[result['request_id']]
                if old != digest: raise ValueError('背景调整请求身份被不同内容复用')
                self.pending['result'] = {**deepcopy(receipt), 'replayed': True}; return False
            reason = self.engine._guard_editable('studio background')
            if reason: raise ValueError(reason)
            preview = preview_controller(self.engine, self.emit)
            value, stage = preview.prepare(p)
            self.pending.update(value=value, stage=stage)
            preview.cancel()
            return True
        except Exception as error:
            result['error'] = error_text(error); return False

    def apply(self, p):
        pending = self.pending
        if pending is None or 'value' not in pending: raise ValueError('背景调整修改没有已显示的最终效果')
        e, pipe, result = self.engine, self.engine._vram, pending['result']
        previous = S.check(getattr(e, '_studio_background', None))
        old_stage, old_key = pipe.studio_background, getattr(pipe, '_studio_background_key', None)
        try:
            pending['started'] = True
            e._studio_background, pipe.studio_background = pending['value'], pending['stage']
            pipe._studio_background_key = pending['stage'].verified_source_key
            frame = e._write_current_frame('studio_background'); frame['doc_state'] = e.doc_state(); self.emit(frame)
            result.update(success=True, no_change=(previous == e._studio_background))
        except Exception as error:
            e._studio_background, pipe.studio_background, pipe._studio_background_key = previous, old_stage, old_key
            try:
                frame = e._write_current_frame('studio_background_rollback'); frame['doc_state'] = e.doc_state(); self.emit(frame)
            except Exception:
                result.update(outcome_unknown=True, requires_reload=True); e._vram = None
            result['error'] = error_text(error)

    def finish(self, p, dispatch_error=None):
        pending, self.pending = self.pending, None
        if pending is None: return
        result = pending['result']
        if dispatch_error: result.update(success=False, error=error_text(dispatch_error), outcome_unknown=pending['started'])
        if result['success'] and not result.get('replayed'):
            try:
                state = self.engine.doc_state()
                if state['document_id'] != result['document_id']: raise ValueError('背景调整完成后照片改变')
                result['history'] = {k: state['history'][k] for k in ('undo_steps', 'redo_steps')}
            except Exception as error: result.update(success=False, outcome_unknown=True, error=error_text(error))
        rid, digest = result.get('request_id'), pending['digest']
        if rid and digest and rid not in self.cache:
            self.cache[rid] = (digest, deepcopy(result))
            while len(self.cache) > 64: self.cache.popitem(last=False)
        self.emit(result)


def controller(engine, emit):
    owner = engine.__dict__.get('_studio_background_owner')
    if owner is None: owner = engine._studio_background_owner = StudioBackgroundController(engine, emit)
    return owner
