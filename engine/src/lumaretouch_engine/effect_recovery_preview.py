"""Read-only, producer-rendered before/after review for one retained mutation.

Source LRCP pixels authorize coordinates only. These PNGs are actual production
pipeline renders, not mask overlays. Neither review image is an edit parameter.
"""
import base64
import io
import json
import re
from copy import deepcopy
from . import effect_recovery_state as S, effect_recovery_runtime as R
from . import people_recovery as PEOPLE
from .source_patch_controller import PROOF_KEYS

MAX_IMAGE_EDGE = 800
MAX_REVIEW_BYTES = 6 * 1024 * 1024


def preview_id(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{32}', value) or int(value, 16) == 0:
        raise ValueError('恢复预览身份无效')
    return value


def image(pixels, presentation):
    from PIL import Image
    from .quant import quantize_t
    rgba = quantize_t(pixels[0].permute(1, 2, 0)).contiguous().cpu().numpy()
    factor = min(1., MAX_IMAGE_EDGE / max(presentation.width, presentation.height))
    dimensions = (max(1, round(presentation.width * factor)), max(1, round(presentation.height * factor)))
    picture = Image.fromarray(rgba, 'RGB').resize(dimensions, Image.Resampling.BILINEAR)
    buffer = io.BytesIO()
    picture.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii'), dimensions


def render_review(engine, stage):
    from .fabric_controller import sync as fabric
    from .local_mask_state import sync as masks
    from .local_grade_runtime import sync as grades
    from .manual_liquify_runtime import sync as manual
    fabric(engine)
    masks(engine, strict=True)
    grades(engine, strict=True)
    R.sync(engine, strict=True)
    manual(engine, strict=True)
    from .studio_background_runtime import sync as studio
    studio(engine, strict=True)
    from .sky_replacement_runtime import sync as sky
    sky(engine,strict=True)
    from .optics_runtime import sync as optics
    optics(engine,strict=True)
    if PEOPLE.managed(engine):
        engine._people_sync(strict=True)
    pipe = engine._vram
    old = pipe.effect_recovery
    old_people = {key: getattr(pipe, key, None) for key in
                  ('people_prepared', 'people_origin', 'people_warp', 'people_suspended')}
    candidate = getattr(stage, 'people_recovery', None)
    strength, channel = engine._retouch_render_args()
    presentation = engine._frame_presentation()
    try:
        before, dimensions = image(pipe.retouch(strength, channel=channel, **engine._params), presentation)
        pipe.effect_recovery = stage
        if candidate is not None:
            PEOPLE.assert_context(engine, candidate['context'])
            from .people_pipeline import install
            install(pipe, candidate['prepared'])
            pipe.people_suspended = None
        after, after_dimensions = image(pipe.retouch(strength, channel=channel, **engine._params), presentation)
        if after_dimensions != dimensions:
            raise ValueError('恢复预览构图在渲染中变化')
    finally:
        pipe.effect_recovery = old
        for key, value in old_people.items():
            setattr(pipe, key, value)
    if len(before) + len(after) > MAX_REVIEW_BYTES:
        raise ValueError('恢复效果对比超过 6 MiB 预览预算')
    return {'before': before, 'after': after, 'width': dimensions[0], 'height': dimensions[1],
            'domain': 'production-output', 'quality': 'proxy-render-srgb8',
            'note': '真实全效果代理渲染；不是原图混合或蒙版示意，也不是全尺寸验收'}


class RecoveryPreview:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.record = None

    def cancel(self):
        self.record = None

    def _matching(self, p):
        owner = self.engine._source_patch_controller().capture
        capture = owner._matching(p, recipe=True)
        if not capture['eligible'] or capture['descriptor']['domain'] != 'source-input':
            raise ValueError('请先显示并确认原始源图定位画面')
        return capture

    def handle(self, p):
        event = {'event': 'effect_recovery_preview', 'protocol': 1,
                 'preview_id': p.get('preview_id'), **{k: p.get(k) for k in PROOF_KEYS},
                 'state': 'failed', 'success': False}
        try:
            action = p.get('action')
            fields = {'cmd', 'action', 'preview_id', *PROOF_KEYS}
            if action == 'preview':
                fields.add('mutation')
            if p.get('cmd') != 'effect_recovery_preview' or action not in ('preview', 'presented', 'cancel') or set(p) != fields:
                raise ValueError('恢复预览命令字段无效')
            ident = preview_id(p['preview_id'])
            capture = self._matching(p)
            proof = {k: p[k] for k in PROOF_KEYS}
            if action == 'preview':
                self.cancel()
                if len(json.dumps(p, allow_nan=False).encode()) > 131072:
                    raise ValueError('恢复笔迹超过 128 KiB')
                mutation = p['mutation']
                viewing = (type(mutation) is dict and mutation.get('action') == 'view')
                if PEOPLE.managed(self.engine):
                    self.engine._people_sync(strict=True)
                if viewing:
                    if set(mutation) != {'action', 'target'}:
                        raise ValueError('恢复查看请求字段无效')
                    S.target(mutation['target'])
                    value = (PEOPLE.value(self.engine) if PEOPLE.handles(self.engine, mutation['target'])
                             else S.check(getattr(self.engine, '_effect_recovery', None)))
                else:
                    value = S.prepare_mutation(self.engine, capture, mutation)
                from .creative_derived_recovery import GLOBAL_TARGETS, global_context, assert_review
                global_proof = global_context(self.engine, mutation['target']) if mutation['target'] in GLOBAL_TARGETS else None
                stage = R.prepare_stage(self.engine, value)
                stage.people_recovery = PEOPLE.prepare(self.engine, value, mutation['target'])
                result = render_review(self.engine, stage)
                self._matching(p)
                candidate_record = {'id': ident, 'proof': proof, 'value': value,
                               'target': p['mutation']['target'], 'presented': False,
                               'people_context': (deepcopy(stage.people_recovery['context'])
                                                  if stage.people_recovery is not None else None),
                               'global_context': deepcopy(global_proof),
                               'committable': not viewing}
                assert_review(self.engine, candidate_record)
                self.record = candidate_record
                event.update(state='ready', success=True, result=result, target=p['mutation']['target'])
            else:
                record = self.record
                if record is None or record['id'] != ident or record['proof'] != proof:
                    raise ValueError('恢复效果预览已失效')
                if action == 'cancel':
                    self.cancel()
                    event.update(state='cancelled', success=True)
                else:
                    from .creative_derived_recovery import assert_review
                    assert_review(self.engine, record)
                    record['presented'] = True
                    event.update(state='presented', success=True)
        except Exception as error:
            self.cancel()
            event['error'] = str(error)[:2000]
        self.emit(event)

    def prepare(self, p):
        self._matching(p)
        record = self.record
        if (record is None or record['id'] != p.get('preview_id') or not record['presented'] or not record['committable']
                or record['proof'] != {k: p[k] for k in PROOF_KEYS}):
            raise ValueError('请先查看此笔真实效果预览，不能提交未显示或过期的修改')
        from .creative_derived_recovery import assert_review
        assert_review(self.engine, record)
        value = S.check(record['value'])
        stage = R.prepare_stage(self.engine, value)
        if PEOPLE.handles(self.engine, record['target']):
            if record['people_context'] is None:
                raise ValueError('人物恢复预览缺少确切人物归属，请重新查看本笔')
            stage.people_recovery = PEOPLE.prepare(self.engine, value, record['target'],
                                                    expected=record['people_context'])
        elif record['people_context'] is not None:
            raise ValueError('人物恢复处理路径在预览后改变')
        return deepcopy(value), stage


def controller(engine, emit):
    owner = engine.__dict__.get('_effect_recovery_preview_owner')
    if owner is None:
        owner = engine._effect_recovery_preview_owner = RecoveryPreview(engine, emit)
    return owner
