"""Transient numeric local grades on the actual main-canvas render path.

Only commit changes the recipe/history. A preview borrows the retained source
mask tensors and replaces four scalars, then restores the canonical stage in a
finally block. Geometry/SAM still use their existing capture-proof commands.
"""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json
import re

from . import local_grade_layers as L, local_grade_runtime as R, local_mask_state as M
from .local_grade_live_dependencies import snapshot as dependency_snapshot

IDENTITY = ('document_id', 'session_id', 'group_id')
BASE_KEYS = {'cmd', 'action', 'request_id', *IDENTITY}


def identifier(value, limit=128):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,%d}' % limit, value):
        raise ValueError('局部调色请求身份无效')
    return value


class LiveLocalGrade:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.session = None
        self.receipts = OrderedDict()
        self.retired = OrderedDict()

    def context(self):
        e = self.engine
        reason = e._guard_editable('local grade')
        if reason:
            raise ValueError(reason)
        if not 0 <= e._doc_index < len(e._docs):
            raise ValueError('没有活动照片')
        row = e._docs[e._doc_index]
        version = e._document_versions().version(row)
        stamp = M.file_stamp(row['path'])
        if row.get('_local_source_stamp') != stamp:
            raise ValueError('源文件已变化，请重新打开照片')
        from .creative_derived_source import record,binding
        effective=None if record(e) is None else tuple(sorted(binding(e).items()))
        return (str(e._load_id), version.document_id, version.revision,
                id(e._vram), id(row), stamp,effective)

    def retire(self):
        old, self.session = self.session, None
        if old:
            self.retired[old['session_id']] = True
            while len(self.retired) > 64:
                self.retired.popitem(last=False)
        return old

    def invalidate(self):
        """Called before another command, not after it has changed the document."""
        old = self.retire()
        if old and old['previewed'] and str(self.engine._load_id) == old['document_id']:
            # No recipe rollback is needed: previews never wrote the recipe.
            try:
                frame = self.engine._write_current_frame('local_grade_cancel')
                self.emit(frame)
            except Exception:
                self.engine._vram = None
                raise

    def matching(self, p):
        s = self.session
        if not s or any(s[key] != p[key] for key in IDENTITY):
            raise ValueError('本次局部调色手势已结束或照片已改变')
        if self.context() != s['context'] or L.check(self.engine._local_grade_layers) != s['before']:
            raise ValueError('照片、源图或调色组已改变，本次未提交调整已失效')
        return s

    def cached_sync(self, groups):
        """Runtime may reuse only this session's already verified stage.

        No cache survives commit, cancellation or an unrelated command. A
        changed file/model stamp fails the gesture instead of silently waiting
        for the next interaction to check its bytes.
        """
        s = self.session
        if not s or s.get('committing') or groups != s['before']:
            return False
        pipe = self.engine._vram
        if (self.context() != s['context'] or dependency_snapshot(self.engine, groups) != s['dependencies']
                or pipe is not s['pipe'] or pipe.src_f32 is not s['source_tensor']
                or pipe.local_grade_layers is not s['stage'] or pipe.local_grade_layers.suspended
                or [(ident, id(weight)) for ident, _, weight in pipe.local_grade_layers.fields] != s['weights']):
            raise ValueError('调色源图、模型或蒙版缓存已变化，本次预览已失效')
        return True

    def preview(self, s, values):
        e = self.engine
        R.sync(e, strict=True)
        stage = e._vram.local_grade_layers
        canonical = stage.fields
        # A disabled group intentionally produces the unchanged photo. No
        # missing mask is promoted to full-image coverage.
        transient = [(ident, tuple(values) if ident == s['group_id'] else grade, weight)
                     for ident, grade, weight in canonical]
        stage.fields = transient
        try:
            # The recipe/cache key is unchanged, so ordinary sync retains these
            # tensors. All LUT, legacy grade, background and geometry ordering
            # remains in the one existing renderer, not a JS approximation.
            # Even a failed readback/post-render dependency check may have
            # touched the visible frame. Cancellation must restore it then.
            s['previewed'] = True
            frame = e._write_current_frame('local_grade_preview')
            if e._vram.local_grade_layers is not stage or stage.fields is not transient:
                raise ValueError('局部调色渲染上下文改变，请重新开始')
            if dependency_snapshot(e, s['before']) != s['dependencies']:
                raise ValueError('源图或模型在预览期间改变，本次调整已取消')
        finally:
            stage.fields = canonical
        s['last'] = list(values)
        self.emit(frame)
        return frame

    def commit(self, s):
        e = self.engine
        groups = deepcopy(s['before'])
        layer = next(layer for layer in groups['layers'] if layer['id'] == s['group_id'])
        layer['grade'] = list(s['last'])
        changed = groups != s['before']
        before = e._history_capture()
        s['committing'] = True  # Persistence always performs full byte checks.
        try:
            if dependency_snapshot(e, s['before']) != s['dependencies']:
                raise ValueError('源图或模型在手势期间改变，不能保留本次调色')
            if changed:
                # The conservative document fence is advanced only once, after
                # the old identity has passed validation and before mutation.
                e._fence_current_document()
                e._local_grade_layers = L.check(groups)
            R.sync(e, strict=True)
            frame = e._write_current_frame('local_grade_commit')
            if dependency_snapshot(e, groups) != s['dependencies']:
                raise ValueError('源图或模型在提交期间改变，本次调色已还原')
        except Exception:
            e._local_grade_layers = s['before']
            e._vram._local_grade_layers_key = None
            self.emit(e._write_current_frame('local_grade_rollback'))
            raise
        if changed:
            s['persistent_outcome_unknown'] = True
            e._history_record('local_grade:' + s['session_id'], before, coalesce=False)
        self.retire()
        frame['doc_state'] = e.doc_state()
        self.emit(frame)
        return changed

    def handle(self, p):
        result = {'event': 'local_grade_live_result', 'protocol': 1,
                  'action': p.get('action'), 'request_id': p.get('request_id'),
                  **{key: p.get(key) for key in IDENTITY},
                  'success': False, 'outcome_unknown': False, 'requires_reload': False}
        digest = None
        commit_session = None
        try:
            action = p.get('action')
            keys = BASE_KEYS | ({'grade'} if action in ('begin', 'preview') else set())
            if p.get('cmd') != 'local_grade_live' or action not in ('begin', 'preview', 'commit', 'cancel') or set(p) != keys:
                raise ValueError('局部调色实时命令字段无效')
            for key in ('request_id', *IDENTITY):
                identifier(p[key], 64 if key == 'group_id' else 128)
            raw = json.dumps(p, sort_keys=True, allow_nan=False).encode()
            if len(raw) > 4096:
                raise ValueError('局部调色命令过大')
            digest = sha256(raw).hexdigest()
            prior = self.receipts.get(p['request_id'])
            if prior:
                if digest != prior[0]:
                    raise ValueError('局部调色请求 ID 已被其他内容使用')
                self.emit(deepcopy(prior[1]))
                return
            if action == 'begin':
                if self.session or p['session_id'] in self.retired:
                    raise ValueError('请先结束当前调色手势，并使用新的手势身份')
                context = self.context()
                if context[0] != p['document_id']:
                    raise ValueError('照片已改变')
                groups = L.check(self.engine._local_grade_layers)
                layer = next((layer for layer in groups['layers'] if layer['id'] == p['group_id']), None)
                if layer is None or layer['grade'] != list(L.grade(p['grade'])):
                    raise ValueError('调色组已改变，请等待当前照片参数刷新')
                dependencies = dependency_snapshot(self.engine, groups)
                R.sync(self.engine, strict=True)
                if dependency_snapshot(self.engine, groups) != dependencies:
                    raise ValueError('源图或模型在调色验证期间改变，请重新开始')
                pipe = self.engine._vram
                self.session = {**{key: p[key] for key in IDENTITY}, 'context': context,
                                'before': groups, 'last': list(layer['grade']), 'previewed': False,
                                'dependencies': dependencies, 'pipe': pipe, 'source_tensor': pipe.src_f32,
                                'stage': pipe.local_grade_layers,
                                'weights': [(ident, id(weight)) for ident, _, weight in pipe.local_grade_layers.fields]}
                result['grade'] = list(layer['grade'])
            elif action == 'cancel':
                # Cancellation is harmless after an external edit already
                # invalidated this session. It must not cancel a newer one.
                if self.session and all(self.session[key] == p[key] for key in IDENTITY):
                    self.invalidate()
                result['cancelled'] = True
            else:
                s = self.matching(p)
                if action == 'preview':
                    values = L.grade(p['grade'])
                    frame = self.preview(s, values)
                    result.update(grade=list(values), frame_seq=str(frame['seq']))
                else:
                    commit_session = s
                    changed = self.commit(s)
                    result.update(no_change=not changed, grade=list(s['last']),
                                  history=self.engine._history_report())
            result['success'] = True
        except Exception as error:
            result['error'] = str(error)[:2000]
            try:
                if self.session and all(self.session[key] == p.get(key) for key in IDENTITY):
                    self.invalidate()
            except Exception as restore_error:
                result.update(outcome_unknown=True, requires_reload=True,
                              error=result['error'] + '; 恢复画面失败：' + str(restore_error)[:1000])
                self.engine._vram = None
            # A failure after history recording/receipt assembly cannot safely
            # be claimed to have left the persistent document unchanged.
            if commit_session and commit_session.get('persistent_outcome_unknown'):
                result['outcome_unknown'] = True
        rid = p.get('request_id')
        if digest and rid not in self.receipts:
            self.receipts[rid] = (digest, deepcopy(result))
            while len(self.receipts) > 64:
                self.receipts.popitem(last=False)
        self.emit(result)


def controller(engine, emit):
    owner = engine.__dict__.get('_local_grade_live_owner')
    if owner is None:
        owner = engine._local_grade_live_owner = LiveLocalGrade(engine, emit)
    return owner
