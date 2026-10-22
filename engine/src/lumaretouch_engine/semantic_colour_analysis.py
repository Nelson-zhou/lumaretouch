# SPDX-License-Identifier: GPL-3.0-or-later
"""Real six-class inference on the exact frozen render, never the source path.

Inference view only is RGB8. Fitting samples are actual full-precision source
locations in the rendered float canvas. No masks are obtained from old resolvers.
"""
from hashlib import sha256
from pathlib import Path
from copy import deepcopy
import importlib.metadata
import numpy as np
from . import semantic_colour_state as S
PINNED_SHA = 'c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0'
MODEL = 'mediapipe-selfie-multiclass-six-classes-v1'
LIMIT = 262144


def check_receipt(v):
    expected = {'backend','model_sha256','runtime','target_input_sha256','reference_input_sha256','classes','analysis_policy'}
    if type(v) is not dict or set(v) != expected or v['backend'] != MODEL or v['classes'] != list(S.CLASSES) or v['analysis_policy'] != 'bounded-rgb8-view-full-float-spatial-samples-v1':
        raise ValueError('AI 追色真实模型分析证据不匹配')
    for key in ('model_sha256','target_input_sha256','reference_input_sha256'): S.digest(v[key])
    if v['model_sha256'] != PINNED_SHA: raise ValueError('AI 追色模型不是已核对许可的固定六类权重')
    if type(v['runtime']) is not str or not 1 <= len(v['runtime']) <= 80: raise ValueError('AI 追色实际运行库身份缺失')
    return deepcopy(v)

def view(frame):
    from .semantic_colour_canvas import validate
    import cv2
    frame = validate(frame); rgb = frame.rgb; h,w = rgb.shape[:2]
    scale = min(1., 512/max(h,w), (LIMIT/(h*w))**.5)
    ah,aw = max(1,round(h*scale)),max(1,round(w*scale))
    reduced = cv2.resize(rgb, (aw,ah), interpolation=cv2.INTER_AREA)
    image = np.ascontiguousarray(np.rint(np.clip(reduced,0,1)*255),dtype=np.uint8)
    # Pixel-centre sampling from the actual float canvas, not the rounded view.
    yy = np.minimum(h-1,((np.arange(ah)+.5)*h/ah).astype(np.int64))
    xx = np.minimum(w-1,((np.arange(aw)+.5)*w/aw).astype(np.int64))
    samples = np.ascontiguousarray(rgb[yy[:,None],xx[None,:]],dtype=np.float32)
    return image,samples

def infer(image):
    """Only call in the bounded disposable offline worker."""
    if type(image) is not np.ndarray or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3 or image.shape[0]*image.shape[1] > LIMIT:
        raise ValueError('AI 追色推理输入不是冻结画布的有界 RGB8 视图')
    from .face import model_search_dirs, SELFIE_MULTICLASS_MODEL
    paths = [Path(p)/SELFIE_MULTICLASS_MODEL for p in model_search_dirs(None)]
    path = next((p for p in paths if p.is_file()), None)
    if path is None: raise ValueError('AI 追色缺少真实六类人像模型，不会替换成直方图或占位蒙版')
    with path.open('rb') as stream: raw = stream.read(64*1024*1024+1)
    if sha256(raw).hexdigest() != PINNED_SHA: raise ValueError('AI 追色模型字节与已许可固定权重不符')
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    from .semantic_masks import skin_from_multiclass
    import cv2
    options = vision.ImageSegmenterOptions(base_options=mp_python.BaseOptions(model_asset_buffer=raw),
        output_confidence_masks=True,output_category_mask=False)
    with vision.ImageSegmenter.create_from_options(options) as segmenter:
        result = segmenter.segment(mp.Image(image_format=mp.ImageFormat.SRGB,data=image))
        planes = []
        for plane in list(getattr(result,'confidence_masks',None) or []):
            value = plane.numpy_view
            planes.append(np.array(value() if callable(value) else value,copy=True,dtype=np.float32).squeeze())
        skin_from_multiclass(planes)  # Validates real six-class probability contract.
    shape = (image.shape[1],image.shape[0])
    probabilities = np.stack([cv2.resize(p,shape,interpolation=cv2.INTER_LINEAR) for p in planes],axis=-1)
    if not np.allclose(probabilities.sum(-1),1.,atol=1e-4,rtol=0): raise ValueError('六类概率缩放后不守恒')
    return probabilities, {'model_sha256':PINNED_SHA,'runtime':importlib.metadata.version('mediapipe'),
                           'input_sha256':sha256(str(image.shape).encode()+image.tobytes()).hexdigest()}

def samples(rgb, probabilities, selection=None):
    """Deterministic spatial stratification, preserving full-precision RGB."""
    if rgb.shape != probabilities.shape[:2]+(3,) or probabilities.shape[-1] != 6: raise ValueError('AI 追色样本与语义概率未对齐')
    weights = np.maximum(probabilities*2-1,0)
    if selection is not None:
        if selection.shape != rgb.shape[:2]: raise ValueError('双图选区未对齐自己的冻结画布')
        weights *= selection[...,None]
    rows = []; coverage = []
    flat = rgb.reshape(-1,3)
    for c in range(6):
        field = weights[...,c].ravel(); indices = np.flatnonzero(field>.05)
        coverage.append({'class':S.CLASSES[c], 'usable_pixels':int(len(indices)),
                         'weighted_coverage':float(field.mean())})
        if len(indices)<32: continue
        chosen = indices[np.linspace(0,len(indices)-1,min(1024,len(indices)),dtype=np.int64)]
        rows.append(np.column_stack((flat[chosen],np.full(len(chosen),c),field[chosen])))
    if not rows: raise ValueError('两图选区没有足够可用语义支持；请修改选区或更换样片')
    return np.ascontiguousarray(np.concatenate(rows),dtype=np.float64),weights,coverage
