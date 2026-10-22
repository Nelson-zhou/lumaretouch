"""Per-source portrait-category inference for independent local-grade groups.

Only the analysis branch is RGB8. The retained mask compositor and image grade
consumer keep their existing float source/master paths. No face identity or
generic subject inference is invented from the six-class portrait model.
"""
from collections import OrderedDict
import hashlib
from pathlib import Path
import threading
import numpy as np
from . import local_mask_state as M
from .semantic_sources import probability_sources, edit_sources

_CACHE = OrderedDict()
_LOCK = threading.RLock()
ANALYSIS_PIXELS = 262_144


def model_bytes(owner):
    from .face import model_search_dirs, SELFIE_MULTICLASS_MODEL
    if (type(owner) is not dict or owner.get('backend') != 'mediapipe'
            or not str(owner.get('contract', '')).startswith(M.SEMANTIC_CONTRACT + ':')):
        raise ValueError('局部语义组需要兼容的真实六类人像模型，不提供占位或通用主体回退')
    paths = [Path(folder) / SELFIE_MULTICLASS_MODEL for folder in model_search_dirs(None)]
    path = next((path for path in paths if path.is_file()), None)
    if path is None: raise ValueError('缺少局部语义组所需的六类人像模型；未下载或替换模型')
    with path.open('rb') as stream: raw = stream.read(64 * 1024 * 1024 + 1)
    if not raw or len(raw) > 64 * 1024 * 1024: raise ValueError('语义模型超过 64 MiB 有界读取预算')
    digest = hashlib.sha256(raw).hexdigest()
    if owner['contract'] != M.SEMANTIC_CONTRACT + ':' + digest:
        raise ValueError('目标可用语义模型与源组实际模型 SHA-256 不同，请重新分析或使用匹配模型')
    return raw, digest


def fields(mask, path, shape, *, force=False, cancelled=lambda: False):
    value = M.check(mask)
    _, channels = M.R.dependencies(value['recipe'])
    if not channels: return {}
    from .semantic_sources import SOURCE_LABELS
    if any(channel not in SOURCE_LABELS for channel in channels):
        raise ValueError('局部语义组含当前人像模型未提供的类别')
    if cancelled(): raise InterruptedError('局部语义重算已取消')
    M.verify_source(value, path)
    raw, digest = model_bytes(value['semantic_owner'])
    source = value['source']
    if source is None: raise ValueError('局部语义组缺少源照片身份')
    key = (source['sha256'], source['width'], source['height'], digest, M.file_stamp(path), ANALYSIS_PIXELS)
    with _LOCK:
        probabilities = None if force else _CACHE.get(key)
    if probabilities is None:
        from .decode import load_rgb
        decoded = load_rgb(path, ANALYSIS_PIXELS)
        if (decoded.src_w, decoded.src_h) != (source['width'], source['height']):
            raise ValueError('局部语义重算的源图尺寸与绑定不符')
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
        # Hash and supply the SAME immutable model buffer; do not reopen a
        # replaceable path or borrow source-photo/category raster assets.
        options = vision.ImageSegmenterOptions(base_options=mp_python.BaseOptions(model_asset_buffer=raw),
            output_confidence_masks=True, output_category_mask=False)
        with vision.ImageSegmenter.create_from_options(options) as segmenter:
            result = segmenter.segment(mp.Image(image_format=mp.ImageFormat.SRGB,
                                                data=np.ascontiguousarray(decoded.rgb)))
            values = []
            for plane in list(getattr(result, 'confidence_masks', None) or []):
                view = plane.numpy_view
                values.append(np.array(view() if callable(view) else view, copy=True))
            probabilities = probability_sources(values)
        M.verify_source(value, path, (decoded.src_h, decoded.src_w))
        if cancelled(): raise InterruptedError('局部语义重算已取消')
        with _LOCK:
            _CACHE[key] = probabilities
            _CACHE.move_to_end(key)
            while len(_CACHE) > 16: _CACHE.popitem(last=False)
    from .face import _resize_float
    h, w = M.R._shape(shape)
    return edit_sources({name: _resize_float(probabilities[name], h, w) for name in channels})


def verify(groups, path):
    for layer in groups['layers']:
        if not layer['enabled']: continue
        M.verify_source(layer['mask'], path)
        if M.R.dependencies(layer['mask']['recipe'])[1]: model_bytes(layer['mask']['semantic_owner'])
