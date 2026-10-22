"""One rendered sky draft, one history transaction, one terminal receipt."""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json
from . import sky_replacement_state as S, sky_replacement_runtime as R, local_mask_state as B
from .sky_replacement_preview import controller as preview_controller, ident
from .white_balance_controller import identity, error_text
KEYS = {'cmd', 'action', 'request_id', 'preview_id', 'session_id', 'document_id'}


class SkyReplacementController:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.pending = None
        self.cache = OrderedDict()

    def prepare(self, p):
        result = {'event': 'sky_replacement_result', 'protocol': 1, 'action': 'apply',
                  **{k: identity(p.get(k), 128) for k in ('request_id', 'preview_id', 'session_id', 'document_id')},
                  'success': False, 'outcome_unknown': False, 'requires_reload': False}
        self.pending = {'result': result, 'digest': None, 'started': False}
        try:
            if set(p) != KEYS or p['cmd'] != 'sky_replacement' or p['action'] != 'apply': raise ValueError('换天空提交字段无效')
            ident(p['preview_id']); ident(p['session_id'])
            if result['request_id'] is None: raise ValueError('换天空请求身份无效')
            digest = self.pending['digest'] = sha256(json.dumps(p, sort_keys=True, allow_nan=False).encode()).hexdigest()
            if result['request_id'] in self.cache:
                old, receipt = self.cache[result['request_id']]
                if old != digest: raise ValueError('换天空请求身份被不同内容复用')
                self.pending['result'] = {**deepcopy(receipt), 'replayed': True}; return False
            reason = self.engine._guard_editable('sky replacement')
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
        if pending is None or 'value' not in pending: raise ValueError('换天空修改没有已显示的最终效果')
        e, pipe, result = self.engine, self.engine._vram, pending['result']
        previous = S.check(getattr(e, '_sky_replacement', None))
        old_stage, old_key = pipe.sky_replacement, getattr(pipe, '_sky_replacement_key', None)
        try:
            R.verified_value(e,pending['value'])
            if pending['value']['enabled'] and B.file_stamp(pending['value']['asset']['path']) != pending['stage'].asset_stamp:
                raise ValueError('素材在最终预览后变化，请重新预览，不能提交旧效果')
            pending['started'] = True
            e._sky_replacement, pipe.sky_replacement = pending['value'], pending['stage']
            pipe._sky_replacement_key = R.stage_key(e, e._sky_replacement)
            frame = e._write_current_frame('sky_replacement')
            R.verified_value(e,e._sky_replacement)
            frame['doc_state'] = e.doc_state(); self.emit(frame)
            result.update(success=True, no_change=(previous == e._sky_replacement))
        except Exception as error:
            e._sky_replacement, pipe.sky_replacement, pipe._sky_replacement_key = previous, old_stage, old_key
            try:
                frame = e._write_current_frame('sky_replacement_rollback'); frame['doc_state'] = e.doc_state(); self.emit(frame)
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
                if state['document_id'] != result['document_id']: raise ValueError('换天空完成后照片改变')
                result['history'] = {k: state['history'][k] for k in ('undo_steps', 'redo_steps')}
            except Exception as error: result.update(success=False, outcome_unknown=True, error=error_text(error))
        rid, digest = result.get('request_id'), pending['digest']
        if rid and digest and rid not in self.cache:
            self.cache[rid] = (digest, deepcopy(result))
            while len(self.cache) > 64: self.cache.popitem(last=False)
        self.emit(result)


def controller(engine, emit):
    owner = engine.__dict__.get('_sky_replacement_owner')
    if owner is None: owner = engine._sky_replacement_owner = SkyReplacementController(engine, emit)
    return owner
