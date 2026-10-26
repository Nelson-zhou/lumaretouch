"""Frozen whole-effective-source locator for spill-only vector drafts.

AUTHORED / UNRUN. The PNGs are bounded display derivatives, never source pixels,
retained masks, or export inputs. No output/proxy/crop inverse is involved.
Only compact ownership evidence and the current vector snapshot are retained.
"""
from copy import deepcopy
from hashlib import sha256
import base64
import io
import math
import time
import uuid

EDGE = 512
MAX_PNG_BYTES = 1024 * 1024
DOMAIN = 'source-normalized'
ACTION = 'id_spill_paint_source'


def dimensions(source):
    """Whole-source display geometry, with explicit positive half-up rounding."""
    from . import local_mask_state as M, local_mask_recipe as R
    checked = M.check({'source': source, 'semantic_owner': None,
                       'recipe': M.empty()['recipe']})['source']
    if checked is None or checked['width'] * checked['height'] > R.MAX_PIXELS:
        raise ValueError('祛染画笔来源超过完整源图尺寸预算')
    scale = min(1., EDGE / max(checked['width'], checked['height']))
    return tuple(max(1, math.floor(checked[key] * scale + .5)) for key in ('width', 'height'))


def _original_pixels(path, source, budget):
    """Decode the bound original at genuine precision, never load_rgb or SHM.

    Match full_candidate_render's existing load_full boundary and orientation.
    Its load_full route supports genuine RGB16 RAW/TIFF/PNG source pixels. Shared
    source-bit admission and working-profile conversion keep the locator equal
    to the actual full candidate inputs rather than inventing another decoder.
    Decoder errors are terminal: no 8-bit, proxy, or alternate-file fallback.
    """
    import numpy as np
    from PIL import Image
    from . import local_mask_state as M
    from .creative_document_assets import MAX_ORIGINAL_BYTES
    from .decode import is_raw, load_full
    from .full_source_working import source_bits, working_rgb, require_opaque_8bit
    before = M.file_stamp(path)
    size = before[2]
    pixels = source['width'] * source['height']
    if size > MAX_ORIGINAL_BYTES or pixels * 96 + size * 2 + 16_777_216 > budget:
        raise ValueError('祛染完整源图解码超过内存预算；不使用代理替代')
    if is_raw(path):
        from .ops import libraw
        header = libraw.identify(path)
        if header is None or header['w'] * header['h'] != pixels:
            raise ValueError('祛染 RAW 完整源图尺寸与当前来源不符')
        bits = 16
    else:
        with Image.open(path) as header:
            if header.width * header.height != pixels or getattr(header, 'n_frames', 1) != 1:
                raise ValueError('祛染原文件完整尺寸或帧数与已绑定来源不符')
            bits = 16 if source_bits(path, header) > 8 else 8
            # Share the full-candidate admission before RGB decoding can drop
            # alpha. RGB16 TIFF independently rejects extra channels.
            if bits == 8:
                require_opaque_8bit(header)
    decoded = load_full(path, max_px=pixels, device='cpu', want_bits=bits)
    if (decoded.draft_used or (decoded.h, decoded.w) != (decoded.src_h, decoded.src_w)
            or (decoded.raw or {}).get('used_preview') or (decoded.raw or {}).get('half_size')
            or decoded.rgb.dtype != (np.uint16 if bits == 16 else np.uint8)):
        raise ValueError('祛染画笔必须使用完整原始精度解码，而不是代理或嵌入预览')
    rgb = working_rgb(decoded)
    result = rgb.astype(np.float32) / np.float32(65535. if bits == 16 else 255.)
    if M.file_stamp(path) != before or M.source_digest(path) != source['sha256']:
        raise ValueError('祛染原文件在完整解码期间发生变化')
    return result


def source_pixels(engine, source):
    """Actual full unedited source, normalized to encoded working-sRGB f32."""
    import numpy as np
    from . import creative_derived_source as D, creative_document_base as B
    from .creative_document_host import memory_budget
    from .spill_removal_render import source_identity
    dimensions(source)
    budget = memory_budget()
    if source['width'] * source['height'] * 96 + 16_777_216 > budget:
        raise ValueError('祛染完整源图显示超过内存预算；不使用代理替代')
    D.verify(source, engine)
    base = D.record(engine)
    if base is not None:
        # This packaged boundary reads immutable linear-premultiplied RGBA,
        # rejects alpha/HDR, and encodes genuine RGB f32 to sRGB. Do not use
        # display_rgba, analysis_rgb, src_f32 or a repaired/rendered substitute.
        result = B.export_source(base, max_bytes=budget)
    else:
        result = _original_pixels(engine._docs[engine._doc_index]['path'], source, budget)
    if type(result) is not np.ndarray or result.dtype != np.float32:
        raise ValueError('祛染完整源图没有保留真实归一化浮点精度')
    source_identity(result, source, full_source=True)
    D.verify(source, engine)
    return result


def _png(pixels, width, height):
    """Reduce complete float pixels before display-only RGB8 allocation."""
    import numpy as np
    from PIL import Image
    if (type(pixels) is not np.ndarray or pixels.dtype != np.float32 or pixels.ndim != 3
            or pixels.shape[2] != 3 or not 1 <= width <= EDGE or not 1 <= height <= EDGE):
        raise ValueError('祛染显示图需要有界的真实浮点 RGB')
    for start in range(0, len(pixels), 128):
        part = pixels[start:start + 128]
        if not np.isfinite(part).all() or np.any(part < 0.) or np.any(part > 1.):
            raise ValueError('祛染显示图不能裁切 HDR 或无效像素')
    channels = []
    for channel in range(3):
        plane = Image.fromarray(pixels[:, :, channel], 'F')
        try:
            reduced = plane.resize((width, height), Image.Resampling.BOX)
            try:
                channels.append(np.asarray(reduced, dtype=np.float32).copy())
            finally:
                reduced.close()
        finally:
            plane.close()
    reduced = np.stack(channels, axis=2)
    if not np.isfinite(reduced).all() or np.any(reduced < 0.) or np.any(reduced > 1.):
        raise ValueError('祛染显示重采样产生无效像素；未进行裁切')
    display = Image.fromarray(np.floor(reduced * np.float32(255.) + np.float32(.5)).astype(np.uint8), 'RGB')
    try:
        output = io.BytesIO()
        display.save(output, format='PNG')
        raw = output.getvalue()
    finally:
        display.close()
    if len(raw) > MAX_PNG_BYTES:
        raise ValueError('祛染源图 PNG 超过有界传输预算')
    return {'mime': 'image/png', 'width': width, 'height': height,
            'sha256': sha256(raw).hexdigest(), 'base64': base64.b64encode(raw).decode('ascii')}


def _coverage_png(coverage, source, width, height):
    import numpy as np
    from . import spill_removal_coverage as C
    value = (np.ones((height, width), np.float32) if coverage is None
             else C.raster(coverage, (height, width), source=source))
    if (type(value) is not np.ndarray or value.dtype != np.float32
            or value.shape != (height, width) or not np.isfinite(value).all()
            or np.any(value < 0.) or np.any(value > 1.)):
        raise ValueError('祛染源图覆盖显示缺少真实计算范围')
    return _png(np.repeat(value[:, :, None], 3, axis=2), width, height)


class PaintSource:
    def __init__(self, engine):
        self.engine = engine
        self.record = None

    def _proof(self, request):
        from .final_canvas_flip_state import require_processing_capture
        require_processing_capture(self.engine)
        from .spill_removal_review import _context
        from .full_candidate_render import identity
        from . import creative_derived_source as D, local_mask_state as M
        row, document, revision = _context(self.engine, request)
        stamp = M.file_stamp(row['path'])
        source = D.binding(self.engine)
        proof, _, _ = identity(self.engine, row, self.engine._capture_state(), document, revision)
        D.verify(source, self.engine)
        if M.file_stamp(row['path']) != stamp:
            raise ValueError('祛染源图捕获期间原始文件来源变化')
        return {'document_id': request['document_id'], 'recipe_document_id': document,
                'recipe_revision': revision, 'source': source,
                'identity': proof, 'original_stamp': stamp}

    def prepare(self, request):
        self.record = None  # Failed/superseded captures cannot leave an old token eligible.
        if (type(request) is not dict or set(request) != {'cmd', 'action', 'request_id',
                'document_id', 'recipe_document_id', 'recipe_revision'}
                or request['cmd'] != 'background' or request['action'] != ACTION):
            raise ValueError('祛染源图捕获请求字段不完整')
        from . import id_background_state as I, spill_removal_coverage as C
        proof = self._proof(request)
        width, height = dimensions(proof['source'])
        stored = I.spill_of(getattr(self.engine, '_id_background', None))['coverage']
        coverage = None if stored is None else C.verify_source(stored, proof['source'])
        pixels = source_pixels(self.engine, proof['source'])
        image = _png(pixels, width, height)
        del pixels
        coverage_image = _coverage_png(coverage, proof['source'], width, height)
        if self._proof(request) != proof:
            raise ValueError('祛染源图、配方或人物归属在显示准备期间改变')
        record = {**deepcopy(proof), 'token': uuid.uuid4().hex,
                  'coverage': deepcopy(coverage), 'expires': time.monotonic() + 300.}
        self.record = record
        return {'version': 1, 'token': record['token'],
                'recipe_document_id': proof['recipe_document_id'], 'recipe_revision': proof['recipe_revision'],
                'source': deepcopy(proof['source']), 'domain': DOMAIN,
                'image': image, 'coverage': coverage_image}

    def _verify(self, request, token):
        record = self.record
        if (record is None or type(token) is not str or token != record['token']
                or time.monotonic() > record['expires']):
            raise ValueError('祛染源图画布已失效，请重新打开源图')
        expected = {key: record[key] for key in ('document_id', 'recipe_document_id',
                    'recipe_revision', 'source', 'identity', 'original_stamp')}
        if self._proof(request) != expected:
            self.record = None
            raise ValueError('祛染笔迹不属于当前显示的源图、配方或人物归属')
        return record

    def coverage(self, request, paint):
        if type(paint) is not dict or set(paint) != {'token', 'strokes'}:
            raise ValueError('祛染画笔需要当前源图票据与完整笔迹草稿')
        from . import spill_removal_paint_vectors as V
        record = self._verify(request, paint['token'])
        result = V.append(deepcopy(record['coverage']), deepcopy(record['source']), paint['strokes'])
        if self._verify(request, paint['token']) is not record:
            raise ValueError('祛染源图画布在笔迹准备期间已被替换')
        return result


def owner(engine):
    value = engine.__dict__.get('_spill_removal_paint_source_owner')
    if value is None:
        value = engine._spill_removal_paint_source_owner = PaintSource(engine)
    return value
