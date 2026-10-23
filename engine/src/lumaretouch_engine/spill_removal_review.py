"""One-use review of the complete target, not a live apply/undo simulation.

Only compact identity evidence and retained vector intent survive preparation.
Full-resolution float images are released between views; PNG is display-only.
"""
from copy import deepcopy
from hashlib import sha256
import base64
import io
import time
import uuid

BOUNDARIES = [
    '固定审核 alpha 估计原背景与前景颜色，不改变抠图边缘或降低全图饱和度。',
    '不透明边缘反光使用保守颜色先验；深处反光、真实同色衣物和复杂背景不能保证区分。',
    '手工覆盖只限制可信校正，不强迫不确定像素改变；数值、照片画质与性能尚未验收。',
    '强烈的上游改色可能使源图估计方向不再合适，必须检查实际完成画面。',
]


def _context(engine, request):
    if request.get('document_id') != engine._load_id:
        raise ValueError('照片已切换，请重新准备祛反光预览')
    row = engine._docs[engine._doc_index]
    version = engine._document_versions().version(row)
    if (request.get('recipe_document_id') != version.document_id
            or request.get('recipe_revision') != str(version.revision)):
        raise ValueError('配方版本已变化，请重新准备祛反光预览')
    return row, version.document_id, str(version.revision)


def _states(engine, recipe):
    from .id_background_state import check
    before = engine._capture_state()
    candidate = {**before, '_id_background': check(recipe)}
    return before, candidate


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
        raise ValueError('祛反光完整渲染与冻结目标不一致')
    size = proof.get('output_size')
    if (not isinstance(rgb, np.ndarray) or rgb.ndim != 3 or rgb.shape[2] != 3
            or list(reversed(rgb.shape[:2])) != size or not np.isfinite(rgb).all()):
        raise ValueError('祛反光预览缺少真实完整浮点渲染')
    # Reduce the completed float result BEFORE the RGB8 display allocation. No
    # resized pixels enter canonical source, analysis, state or export.
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
        raise ValueError('祛反光显示图超过传输预算；未修改照片')
    compact = {'mime': 'image/png', 'width': width, 'height': height,
               'sha256': sha256(raw).hexdigest()}
    return compact, {**compact, 'base64': base64.b64encode(raw).decode('ascii')}


class Review:
    def __init__(self, engine):
        self.engine = engine
        # A frozen read-only proposal is not an open transaction or worker.
        # It must not block autosave merely because the dialog was dismissed.
        self.review = None

    def preview(self, request):
        from . import id_background_state as I, spill_removal_state as S
        from . import spill_removal_coverage as C, creative_derived_source as D
        engine = self.engine
        self.review = None  # Superseded reviews never remain eligible.
        row, document, revision = _context(engine, request)
        params = request['parameters']
        if type(params) is not dict or set(params) != {'enabled', 'strength'}:
            raise ValueError('祛反光仅接受启用和强度参数')
        value = I.check(getattr(engine, '_id_background', None))
        spill = I.spill_of(value)
        spill.update(params)
        ids = request['coverage_ids']; reviewed = request['coverage_reviewed']
        if type(reviewed) is not bool:
            raise ValueError('手工覆盖确认必须是布尔值')
        if ids is None:
            if reviewed: raise ValueError('保留覆盖不能伪造新的审核确认')
        elif type(ids) is list and not ids:
            if reviewed: raise ValueError('自动范围不能伪造手工审核确认')
            spill['coverage'] = None
        else:
            spill['coverage'] = C.review(engine, ids, reviewed)
        spill = S.check(spill)
        if S.active(spill) and not I.active(value):
            raise ValueError('请先启用具有独立审核主体范围的证件照背景')
        recipe = I.with_spill(value, spill)
        source = D.binding(engine)
        before, candidate = _states(engine, recipe)
        prior, proposed = _identities(engine, row, before, candidate, document, revision)
        left, left_public = _view(engine, row, before, document, revision, prior)
        right, right_public = _view(engine, row, candidate, document, revision, proposed)
        if (left['width'], left['height']) != (right['width'], right['height']):
            raise ValueError('祛反光前后画面几何不一致')
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
            raise ValueError('祛反光预览已过期，请重新检查')
        verify(record['source'], self.engine)
        before, candidate = _states(self.engine, record['recipe'])
        if _identities(self.engine, row, before, candidate, document, revision) != (record['prior'], record['proposed']):
            raise ValueError('祛反光预览后源图、编辑或人物归属发生变化')
        return record

    def claim(self, request):
        record = self.review
        if record is None or request.get('token') != record['token']:
            raise ValueError('祛反光预览不存在、已消费或被新预览替代')
        if (request.get('reviewed') is not True
                or request.get('before_sha256') != record['before']['sha256']
                or request.get('after_sha256') != record['after']['sha256']):
            raise ValueError('必须先查看并确认这组真实前后画面')
        self.verify(record, request)
        self.review = None
        return deepcopy(record)


def owner(engine):
    value = engine.__dict__.get('_spill_removal_review_owner')
    if value is None: value = engine._spill_removal_review_owner = Review(engine)
    return value
