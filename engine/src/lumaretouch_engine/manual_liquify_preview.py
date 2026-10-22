"""Latest-wins cancellable Rust replay; image rendering stays on engine sequence.

The drawing surface contains processed pixels before optics, never a source
locator. A separate final optical render is read-only and must also be presented.
The owned document/projection/optics revision binds both views to one candidate.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import base64
import io
import json
import re
import threading
from . import manual_liquify_state as S, manual_liquify_runtime as R, local_mask_state as M
from .manual_liquify_stage import ManualLiquifyStage
from .manual_liquify_field import replay
from .effect_recovery_preview import image

PREVIEW_PROTOCOL = 2
MAX_REVIEW_BYTES = 12 * 1024 * 1024
MAX_IMAGE_BYTES = 4 * 1024 * 1024

def optics_signature(engine):
    from .optics_state import check
    value = check(getattr(engine, "_optics", None))
    return sha256(json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def ident(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{32}', value) or int(value, 16) == 0:
        raise ValueError('液化会话或预览身份无效')
    return value


def context(engine):
    # Reuse the exact established Projection and document-version source, not
    # the source capture pixels or its eligibility flag.
    metadata, spec = engine._source_patch_controller().capture._context()
    return {**metadata, 'optics_signature': optics_signature(engine)}, spec


def render(engine, stage, baseline=None):
    from .fabric_controller import sync as fabric
    from .local_mask_state import sync as masks
    from .local_grade_runtime import sync as grades
    from .effect_recovery_runtime import sync as recovery
    fabric(engine); masks(engine, strict=True); grades(engine, strict=True); recovery(engine, strict=True); R.sync(engine, strict=True)
    from .studio_background_runtime import sync as studio
    from .optics_runtime import sync as optics
    from .optics_stage import OpticsStage
    from .optics_state import active as optics_active
    studio(engine, strict=True); optics(engine, strict=True)
    signature = optics_signature(engine)
    pipe = engine._vram
    old, old_optics = pipe.manual_liquify, pipe.optics
    optical = optics_active(old_optics.value)
    strength, channel = engine._retouch_render_args()
    presentation = engine._frame_presentation()
    try:
        # Only this main-sequence render temporarily bypasses optics. Neither
        # retained recipe nor document history changes. The source is already
        # processed through background, studio and the existing manual layer.
        pipe.optics = OpticsStage()
        before, dimensions = (image(pipe.retouch(strength, channel=channel, **engine._params), presentation)
                              if baseline is None else baseline)
        pipe.manual_liquify = stage
        after, after_dimensions = image(pipe.retouch(strength, channel=channel, **engine._params), presentation)
        if dimensions != after_dimensions: raise ValueError('液化预览构图变化')
        # Protection belongs to the pre-optics drawable canvas. Only crop and
        # rotate it; neither manual warp nor optical/photo corrections may move
        # or tint this retained destination protection overlay.
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
        pipe.optics = old_optics
        # A neutral optics stage is an exact pass-through. Otherwise render the
        # same candidate through the real optical stage, not an enlarged proxy
        # remap or a coordinate-only approximation of its nonlinear sampling.
        final, final_dimensions = (image(pipe.retouch(strength, channel=channel, **engine._params), presentation)
                                   if optical else (after, dimensions))
    finally:
        pipe.manual_liquify, pipe.optics = old, old_optics
    if optics_signature(engine) != signature: raise ValueError('液化双视图渲染期间镜头/透视状态变化')
    pictures = (before, after, protection, final)
    if any(len(p) > MAX_IMAGE_BYTES for p in pictures) or sum(map(len, pictures)) > MAX_REVIEW_BYTES:
        raise ValueError('液化双视图预览超过每图 4 MiB 或总计 12 MiB')
    return {'before': before, 'after': after, 'protection': protection, 'width': dimensions[0], 'height': dimensions[1],
            'domain': S.DOMAIN, 'quality': 'proxy-render-srgb8', 'drawing_space': 'pre-optics',
            'optics_signature': signature, 'optics_active': bool(optical),
            'final_review': {'after': final, 'width': final_dimensions[0], 'height': final_dimensions[1],
                             'quality': 'proxy-render-srgb8', 'domain': 'final-optical-output', 'read_only': True,
                             'optics_signature': signature},
            'note': '左侧在镜头/透视之前绘制，右侧只读查看同一笔的最终效果；全尺寸按保留矢量重放'}


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
        return {'event': 'manual_liquify_preview', 'protocol': PREVIEW_PROTOCOL, 'preview_id': p.get('preview_id'),
                'session_id': p.get('session_id'), 'document_id': p.get('document_id'),
                'optics_signature': self.session['metadata']['optics_signature'] if self.session else None, **values}

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
                if not viewing and not session['shown']: raise ValueError('液化绘制图与最终光学图尚未确认显示')
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
                    if result['optics_signature'] != self.session['metadata']['optics_signature']:
                        raise ValueError('液化最终光学预览不属于当前会话')
                    # This cache is exclusively the pre-optics, pre-gesture view.
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
