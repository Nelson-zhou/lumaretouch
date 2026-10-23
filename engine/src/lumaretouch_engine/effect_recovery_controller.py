"""One reviewed recovery gesture, one history entry, one terminal receipt."""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json
from . import effect_recovery_state as S, effect_recovery_runtime as R
from .effect_recovery_preview import controller as preview_controller, preview_id
from .source_patch_controller import PROOF_KEYS
from .white_balance_controller import identity, error_text

KEYS = {'cmd', 'action', 'request_id', 'preview_id', *PROOF_KEYS}


class RecoveryController:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.pending = None
        self.cache = OrderedDict()

    def prepare(self, p):
        result = {'event': 'effect_recovery_result', 'protocol': 1, 'action': 'apply',
                  'request_id': identity(p.get('request_id'), 128),
                  'preview_id': identity(p.get('preview_id'), 32),
                  **{k: identity(p.get(k), 128) for k in PROOF_KEYS},
                  'success': False, 'outcome_unknown': False, 'requires_reload': False}
        self.pending = {'result': result, 'digest': None, 'started': False}
        try:
            if set(p) != KEYS or p['cmd'] != 'effect_recovery' or p['action'] != 'apply':
                raise ValueError('恢复提交命令字段无效')
            preview_id(p['preview_id'])
            if result['request_id'] is None or any(result[k] is None for k in PROOF_KEYS):
                raise ValueError('恢复提交身份无效')
            digest = self.pending['digest'] = sha256(json.dumps(p, sort_keys=True, allow_nan=False).encode()).hexdigest()
            if result['request_id'] in self.cache:
                old, receipt = self.cache[result['request_id']]
                if old != digest:
                    raise ValueError('恢复请求 ID 已被不同内容使用')
                self.pending['result'] = {**deepcopy(receipt), 'replayed': True}
                return False
            reason = self.engine._guard_editable('effect recovery')
            if reason:
                raise ValueError(reason)
            preview = preview_controller(self.engine, self.emit)
            value, stage = preview.prepare(p)
            self.pending.update(value=value, stage=stage)
            preview.cancel()
            self.engine._source_patch_controller().capture.invalidate()
            return True
        except Exception as error:
            result['error'] = error_text(error)
            return False

    def apply(self, p):
        pending = self.pending
        if pending is None or 'value' not in pending:
            raise ValueError('恢复提交没有预先验证的效果预览')
        e, pipe = self.engine, self.engine._vram
        previous = S.check(getattr(e, '_effect_recovery', None))
        old_stage, old_key = pipe.effect_recovery, getattr(pipe, '_effect_recovery_key', None)
        result = pending['result']
        try:
            verified_key = pending['stage'].verified_source_key
            from .id_background_recovery import assert_consumer
            assert_consumer(e,pending['stage'])
            from .common_background_recovery import assert_consumer as assert_common
            assert_common(e, pending['stage'])
            if R.stage_key(e, pending['value']) != verified_key:
                raise ValueError('恢复准备后源图改变，未提交本笔')
            pending['started'] = True
            people = getattr(pending['stage'], 'people_recovery', None)
            if people is not None:
                from .people_recovery import commit
                frame = commit(e, people, verified_source_key=verified_key, recovery=pending['value'])
                no_change = people['no_change']
            else:
                e._effect_recovery, pipe.effect_recovery = pending['value'], pending['stage']
                pipe._effect_recovery_key = verified_key
                frame = e._write_current_frame('effect_recovery')
                assert_consumer(e,pending['stage'])
                assert_common(e, pending['stage'])
                if R.stage_key(e, e._effect_recovery) != verified_key:
                    raise ValueError('恢复提交渲染期间源图改变，撤回本笔')
                no_change = previous == e._effect_recovery
            # The dispatcher still has to record this gesture. Publish both
            # pixels and authoritative UI state only after that history step.
            pending['frame'] = frame
            result.update(success=True, no_change=no_change)
        except Exception as error:
            e._effect_recovery, pipe.effect_recovery, pipe._effect_recovery_key = previous, old_stage, old_key
            try:
                frame = e._write_current_frame('effect_recovery_rollback')
                frame['doc_state'] = e.doc_state()
                self.emit(frame)
            except Exception:
                result.update(outcome_unknown=True, requires_reload=True)
                e._vram = None
            result['error'] = error_text(error)

    def finish(self, p, dispatch_error=None):
        pending, self.pending = self.pending, None
        if pending is None:
            return
        result = pending['result']
        if dispatch_error:
            result.update(success=False, error=error_text(dispatch_error), outcome_unknown=pending['started'])
        if result['success'] and not result.get('replayed'):
            try:
                state = self.engine.doc_state()
                if state['document_id'] != result['document_id']:
                    raise ValueError('恢复提交后文档发生变化')
                result['history'] = {k: state['history'][k] for k in ('undo_steps', 'redo_steps')}
                if 'frame' in pending:
                    pending['frame']['doc_state'] = state
                    self.emit(pending['frame'])
            except Exception as error:
                result.update(success=False, outcome_unknown=True, error=error_text(error))
        rid, digest = result.get('request_id'), pending['digest']
        if rid and digest and rid not in self.cache:
            self.cache[rid] = (digest, deepcopy(result))
            while len(self.cache) > 64:
                self.cache.popitem(last=False)
        self.emit(result)


def controller(engine, emit):
    owner = engine.__dict__.get('_effect_recovery_owner')
    if owner is None:
        owner = engine._effect_recovery_owner = RecoveryController(engine, emit)
    return owner
