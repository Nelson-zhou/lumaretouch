"""One-use review of source-owned manual original-shadow extraction.

Both views render complete isolated candidates. Retained lit-floor and shadow
regions are independent geometric snapshots, never inferred or borrowed masks.
Only compact display identities survive preparation, not full source pixels.
"""
from copy import deepcopy
from hashlib import sha256
import base64
import io
import time
import uuid

BOUNDARIES = [
    '手动选择同一均匀漫反射地面的无阴影参考与原阴影保留区；不是 AI 自动识别或通用阴影分离。',
    '纹理、反射、高光、彩色光和变化照明可能被误当作阴影；不适合复杂地面。',
    '两组选区使用独立源图手工矢量；直接画布只显示缩小定位图，完整源图重放笔画后才生成此审核。',
    '原阴影与新投影互斥；仅使用独立审核的主体范围，不借用接触或全部保留范围。',
    '必须检查这组完整渲染的真实前后画面；数值、照片画质与性能尚未验收。',
]


def _context(engine, request):
    if request.get('document_id') != engine._load_id:
        raise ValueError('照片已切换，请重新准备原阴影预览')
    row = engine._docs[engine._doc_index]
    version = engine._document_versions().version(row)
    if (request.get('recipe_document_id') != version.document_id
            or request.get('recipe_revision') != str(version.revision)):
        raise ValueError('配方版本已变化，请重新准备原阴影预览')
    return row, version.document_id, str(version.revision)


def _states(engine, recipe):
    from .id_background_state import check
    before = engine._capture_state()
    return before, {**before, '_id_background': check(recipe)}


def _identities(engine, row, before, candidate, document, revision):
    from .full_candidate_render import identity
    prior, _, _ = identity(engine, row, before, document, revision)
    proposed, _, _ = identity(engine, row, candidate, document, revision)
    return prior, proposed


def _view(engine, row, state, document, revision, expected):
    from .full_candidate_render import render
    from PIL import Image
    import numpy as np
    rgb, proof = render(engine, row, state, document, revision)
    if any(proof.get(key) != value for key, value in expected.items()):
        raise ValueError('原阴影完整渲染与冻结目标不一致')
    if (not isinstance(rgb, np.ndarray) or rgb.ndim != 3 or rgb.shape[2] != 3
            or min(rgb.shape[:2]) < 1 or not np.issubdtype(rgb.dtype, np.floating)
            or list(reversed(rgb.shape[:2])) != proof.get('output_size')
            or not np.isfinite(rgb).all()):
        raise ValueError('原阴影预览缺少真实完整浮点渲染')
    # Resize only the completed result, before allocating its RGB8 display.
    # Neither these resized pixels nor the PNG enters source, state or export.
    h, w = rgb.shape[:2]
    factor = min(1., 512 / max(w, h))
    width, height = max(1, round(w * factor)), max(1, round(h * factor))
    channels = []
    for channel in range(3):
        plane = Image.fromarray(rgb[:, :, channel].astype(np.float32), 'F')
        try:
            small = plane.resize((width, height), Image.Resampling.BILINEAR)
            try: channels.append(np.asarray(small).copy())
            finally: small.close()
        finally: plane.close()
    display = Image.fromarray(np.rint(np.clip(np.stack(channels, axis=2), 0., 1.) * 255).astype(np.uint8), 'RGB')
    try:
        stream = io.BytesIO(); display.save(stream, format='PNG'); raw = stream.getvalue()
    finally: display.close()
    if len(raw) > 1024 * 1024:
        raise ValueError('原阴影显示图超过传输预算；未修改照片')
    compact = {'mime': 'image/png', 'width': width, 'height': height,
               'sha256': sha256(raw).hexdigest()}
    return compact, {**compact, 'base64': base64.b64encode(raw).decode('ascii')}


def _proposal(engine, request):
    from . import id_background_state as I, original_shadow_state as S
    parameters = request['parameters']
    if type(parameters) is not dict or set(parameters) != {'enabled', 'strength', 'blend'}:
        raise ValueError('原阴影仅接受启用、强度与混合方式参数')
    reviewed, confirmed = request['samples_reviewed'], request['uniform_floor_confirmed']
    if type(reviewed) is not bool or type(confirmed) is not bool:
        raise ValueError('原阴影样本审核与均匀地面确认必须是布尔值')
    clear = request.get('clear_samples', False)
    if 'clear_samples' in request and clear is not True:
        raise ValueError('清除原阴影样本字段只能省略或明确为 true')
    paint = request.get('paint')
    if 'paint' in request and paint is None:
        raise ValueError('原阴影画笔不能为空值')
    replacing = request['lit_ids'] is not None or request['retention_ids'] is not None or paint is not None
    if reviewed != replacing:
        raise ValueError('替换原阴影样本需明确审核；保留样本不能伪造新的审核确认')
    value = I.check(getattr(engine, '_id_background', None))
    if clear:
        if (paint is not None or replacing or reviewed or confirmed
                or parameters != {'enabled': False, 'strength': 100, 'blend': 'normal'}
                or parameters['enabled'] is not False):
            raise ValueError('清除样本必须关闭原阴影并恢复中性参数，不能同时提交选区或笔画')
        return I.with_original_shadow(value, S.neutral())
    shadow = I.original_shadow_of(value)
    shadow.update(parameters)
    shadow['uniform_floor_confirmed'] = confirmed
    if paint is not None:
        if request['lit_ids'] is not None or request['retention_ids'] is not None:
            raise ValueError('直接原阴影画笔不能同时替换局部对象选区')
        from .original_shadow_paint_source import owner
        shadow.update(owner(engine).bindings(request, paint))
    else:
        for key, selection in (('lit_floor', 'lit_ids'), ('retention', 'retention_ids')):
            if request[selection] is not None:
                shadow[key] = S.review(engine, request[selection], reviewed)
    shadow = S.check(shadow)
    if shadow['enabled'] and not I.active(value):
        raise ValueError('请先启用具有独立审核主体范围的证件照背景')
    return I.with_original_shadow(value, shadow)


class Review:
    def __init__(self, engine):
        self.engine, self.review = engine, None

    def preview(self, request):
        from . import creative_derived_source as D
        engine = self.engine
        self.review = None
        row, document, revision = _context(engine, request)
        recipe = _proposal(engine, request)
        source = D.binding(engine)
        before, candidate = _states(engine, recipe)
        prior, proposed = _identities(engine, row, before, candidate, document, revision)
        left, left_public = _view(engine, row, before, document, revision, prior)
        right, right_public = _view(engine, row, candidate, document, revision, proposed)
        if (left['width'], left['height']) != (right['width'], right['height']):
            raise ValueError('原阴影前后画面几何不一致')
        record = {'token': uuid.uuid4().hex, 'document_id': request['document_id'],
                  'recipe_document_id': document, 'recipe_revision': revision,
                  'source': source, 'recipe': recipe, 'prior': prior, 'proposed': proposed,
                  'before': left, 'after': right, 'expires': time.monotonic() + 300.}
        self.verify(record, request)
        self.review = record
        return {'version': 1, 'token': record['token'], 'recipe_document_id': document,
                'recipe_revision': revision, 'source': deepcopy(source),
                'candidate_sha256': proposed['candidate_sha256'],
                'before': left_public, 'after': right_public, 'boundaries': BOUNDARIES[:]}

    def verify(self, record, request):
        from .creative_derived_source import verify
        row, document, revision = _context(self.engine, request)
        if (record['document_id'] != request['document_id']
                or record['recipe_document_id'] != document or record['recipe_revision'] != revision
                or time.monotonic() > record['expires']):
            raise ValueError('原阴影预览已过期，请重新检查')
        verify(record['source'], self.engine)
        before, candidate = _states(self.engine, record['recipe'])
        if _identities(self.engine, row, before, candidate, document, revision) != (record['prior'], record['proposed']):
            raise ValueError('原阴影预览后源图、编辑或人物归属发生变化')
        return record

    def claim(self, request):
        record = self.review
        if record is None or request.get('token') != record['token']:
            raise ValueError('原阴影预览不存在、已消费或被新预览替代')
        if (request.get('reviewed') is not True
                or request.get('before_sha256') != record['before']['sha256']
                or request.get('after_sha256') != record['after']['sha256']):
            raise ValueError('必须先查看并确认这组真实前后画面')
        self.verify(record, request)
        self.review = None
        return deepcopy(record)


def owner(engine):
    value = engine.__dict__.get('_original_shadow_review_owner')
    if value is None: value = engine._original_shadow_review_owner = Review(engine)
    return value
