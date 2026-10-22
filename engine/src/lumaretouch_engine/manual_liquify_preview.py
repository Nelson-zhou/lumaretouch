"""Latest-wins cancellable Rust replay; image rendering stays on engine sequence.

Unlike recovery painting, the sole drawing surface is the real processed output.
Its producer-owned projection/revision and presentation acknowledgment authorize
geometry. No source-locator acknowledgment is repurposed as output proof.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import base64
import io
import json
import re
import threading
from . import manual_liquify_state as S, manual_liquify_runtime as R, local_mask_state as M
from .manual_liquify_stage import ManualLiquifyStage
from .manual_liquify_field import replay
from .effect_recovery_preview import image, MAX_REVIEW_BYTES


def ident(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{32}', value) or int(value, 16) == 0:
        raise ValueError('液化会话或预览身份无效')
    return value


def context(engine):
    # Reuse the exact established Projection and document-version source, not
    # the source capture pixels or its eligibility flag.
    metadata, spec = engine._source_patch_controller().capture._context()
    return metadata, spec


def render(engine, stage, baseline=None):
    from .fabric_controller import sync as fabric
    from .local_mask_state import sync as masks
    from .local_grade_runtime import sync as grades
    from .effect_recovery_runtime import sync as recovery
    fabric(engine); masks(engine, strict=True); grades(engine, strict=True); recovery(engine, strict=True); R.sync(engine, strict=True)
    pipe = engine._vram
    old = pipe.manual_liquify
    strength, channel = engine._retouch_render_args()
    presentation = engine._frame_presentation()
    try:
        before, dimensions = (image(pipe.retouch(strength, channel=channel, **engine._params), presentation)
                              if baseline is None else baseline)
        pipe.manual_liquify = stage
        after, after_dimensions = image(pipe.retouch(strength, channel=channel, **engine._params), presentation)
        if dimensions != after_dimensions: raise ValueError('液化预览构图变化')
        # Protection lives at final canvas coordinates. Only crop/rotate it for
        # the display; applying manual warp again would move a fixed protection.
        import numpy as np
        import torch
        from PIL import Image
        field = stage.field
        mask = np.zeros((pipe.h, pipe.w), np.float32) if field is None else field[..., 2]
        projected = pipe.apply_geometry(torch.as_tensor(np.ascontiguousarray(mask), device=pipe.device)[None,None])
        alpha = np.clip(projected[0,0].cpu().numpy()*160, 0, 160).astype(np.uint8)
        rgba = np.zeros((*alpha.shape, 4), np.uint8); rgba[...,0] = 255; rgba[...,3] = alpha
        picture = Image.fromarray(rgba, 'RGBA').resize(dimensions, Image.Resampling.BILINEAR)
        buffer = io.BytesIO(); picture.save(buffer, format='PNG')
        protection = 'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii')
    finally:
        pipe.manual_liquify = old
    if len(before)+len(after)+len(protection) > MAX_REVIEW_BYTES: raise ValueError('液化预览超过 6 MiB')
    return {'before': before, 'after': after, 'protection': protection, 'width': dimensions[0], 'height': dimensions[1],
            'domain': S.DOMAIN, 'quality': 'proxy-render-srgb8', 'note': '真实全效果代理渲染；全尺寸按保留矢量重新计算，不放大此图'}


class LiquifyPreview:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.session = None
        self.record = None
        self.job = None
        self.latest = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='liquify-replay')

    def cancel(self):
        if self.job: self.job['stop'].set()
        self.latest = self.record = self.session = None

    def close(self):
        self.cancel()
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.job = None

    def matching(self, p):
        session = self.session
        metadata, spec = context(self.engine)
        if (session is None or session['id'] != p.get('session_id') or metadata != session['metadata']
                or spec != session['capture']['spec'] or metadata['document_id'] != p.get('document_id')):
            raise ValueError('液化画布或编辑版本已变化，请重新进入工具')
        row = self.engine._docs[self.engine._doc_index]
        if row['path'] != session['path'] or M.file_stamp(session['path']) != session['stamp'] or row.get('_local_source_stamp') != session['stamp']:
            raise ValueError('液化源图在当前手势期间发生变化，请重新打开照片')
        return session

    def event(self, p, **values):
        return {'event': 'manual_liquify_preview', 'protocol': 1, 'preview_id': p.get('preview_id'),
                'session_id': p.get('session_id'), 'document_id': p.get('document_id'), **values}

    def handle(self, p):
        try:
            action = p.get('action')
            fields = {'cmd', 'action', 'preview_id', 'session_id', 'document_id'} | ({'mutation'} if action == 'preview' else set())
            if set(p) != fields or p['cmd'] != 'manual_liquify_preview' or action not in ('preview', 'presented', 'cancel'):
                raise ValueError('液化预览命令字段无效')
            ident(p['preview_id']); ident(p['session_id'])
            if action == 'cancel':
                if self.session and self.session['id'] == p['session_id']: self.cancel()
                self.emit(self.event(p, state='cancelled', success=True)); return
            if action == 'preview':
                if len(json.dumps(p, allow_nan=False).encode()) > 256*1024: raise ValueError('液化预览请求过大')
                viewing = p['mutation'] == {'action': 'view'}
                if self.session is None or self.session['id'] != p['session_id']:
                    if not viewing: raise ValueError('必须先显示当前输出，才能画液化笔迹')
                    self.cancel()
                    metadata, spec = context(self.engine)
                    if metadata['document_id'] != p['document_id']: raise ValueError('液化照片已切换')
                    import torch
                    pipe = self.engine._vram
                    coverage = spec.apply(torch.ones_like(pipe.src_f32[:,:1]))
                    capture = {'spec': spec, 'valid': (coverage[0,0] >= 1-1e-6).contiguous().cpu().numpy(), 'descriptor': metadata}
                    row = self.engine._docs[self.engine._doc_index]
                    stamp = M.file_stamp(row['path'])
                    binding = M.bind_source(self.engine)
                    if M.file_stamp(row['path']) != stamp: raise ValueError('源图在液化会话验证时变化')
                    self.session = {'id': p['session_id'], 'metadata': metadata, 'capture': capture, 'shown': False,
                                    'path': row['path'], 'stamp': stamp, 'binding': binding}
                session = self.matching(p)
                if not viewing and not session['shown']: raise ValueError('液化全效果画布尚未确认显示')
                value = S.check(getattr(self.engine, '_manual_liquify', None)) if viewing else S.prepare_mutation(
                    self.engine, session['capture'], p['mutation'], verified_binding=session['binding'])
                if value['source'] is not None and value['source'] != session['binding']:
                    raise ValueError('液化笔迹不属于当前已验证源照片')
                self.matching(p)
                if self.job: self.job['stop'].set()
                self.record = None
                self.latest = {'request': deepcopy(p), 'value': value, 'committable': not viewing}
                self.tick()
            else:
                self.matching(p)
                record = self.record
                if not record or record['request']['preview_id'] != p['preview_id']: raise ValueError('液化预览已被更新替代')
                record['presented'] = True
                self.session['shown'] = True
                self.emit(self.event(p, state='presented', success=True))
        except Exception as error:
            self.cancel()
            self.emit(self.event(p, state='failed', success=False, error=str(error)[:2000]))

    def tick(self):
        if self.job and self.job['future'].done():
            job, self.job = self.job, None
            if not job['stop'].is_set() and self.session is not None and self.latest is None:
                p = job['request']
                try:
                    self.matching(p)
                    field = job['future'].result()
                    # Full SHA is verified at session admission and final apply.
                    # Intermediate candidates retain that binding and recheck the
                    # document/projection/source stamp, not repeatedly hash RAW.
                    pipe = self.engine._vram
                    stage = ManualLiquifyStage(pipe.device, (pipe.h, pipe.w), pipe.high_precision_warp)
                    stage.set(field, required=bool(job['value']['strokes']))
                    result = render(self.engine, stage, self.session.get('baseline'))
                    self.matching(p)
                    self.session['baseline'] = (result['before'], (result['width'], result['height']))
                    self.record = {**job, 'stage': stage, 'presented': False}
                    self.emit(self.event(p, state='ready', success=True, result=result,
                        recipe_document_id=self.session['metadata']['recipe_document_id'], recipe_revision=self.session['metadata']['recipe_revision']))
                except Exception as error:
                    self.cancel()
                    self.emit(self.event(p, state='failed', success=False, error=str(error)[:2000]))
        if self.job is None and self.latest is not None:
            job, self.latest = self.latest, None
            stop = threading.Event()
            shape = (self.engine._vram.h, self.engine._vram.w)
            job.update(stop=stop, future=self.pool.submit(replay, job['value'], shape, cancelled=stop.is_set))
            self.job = job

    def prepare(self, p):
        self.matching(p)
        record = self.record
        if (record is None or record['request']['preview_id'] != p.get('preview_id')
                or not record['presented'] or not record['committable'] or self.job or self.latest):
            raise ValueError('液化最终效果尚未显示，或已过期；不能提交')
        value = R.verified_value(self.engine, record['value'])
        return deepcopy(value), record['stage']


def controller(engine, emit):
    owner = engine.__dict__.get('_manual_liquify_preview_owner')
    if owner is None:
        owner = engine._manual_liquify_preview_owner = LiquifyPreview(engine, emit)
    return owner
