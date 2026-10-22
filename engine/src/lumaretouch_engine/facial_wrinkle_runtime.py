"""Selected-face analysis lifecycle, independent pre-deform render and export.

Frozen analysis input is the repaired working-sRGB source, NOT a previously
wrinkle-corrected frame. Semantic support can be resampled; measured correction
never is. Full-resolution export solves once before tile extraction.
"""
import hashlib
import re
import numpy as np
from . import facial_wrinkle_state as S
from .facial_wrinkle_layer import FacialWrinkleLayer, bounds, attach_delta


def skin_support(pc):
    if (pc is None or getattr(pc, 'backend', None) != 'mediapipe'
            or not re.fullmatch('[0-9a-f]{64}', str(getattr(pc, 'semantic_model_sha256', None)))):
        return None
    skin = (getattr(pc, 'masks', None) or {}).get('skin')
    if skin is None: return None
    value = np.asarray(skin, np.float32)
    if value.ndim != 2 or not value.size or not np.isfinite(value).all() or np.any((value < 0) | (value > 1)):
        raise ValueError('面部祛纹皮肤语义支持场无效')
    return value


def landmarks_identity(landmarks):
    value = np.asarray(landmarks, dtype='<f4')
    if value.shape != (478, 3) or not np.isfinite(value).all():
        raise ValueError('选中人物身份需要真实的归一化 478×3 关键点')
    if np.any(value[:, :2] < -1) or np.any(value[:, :2] > 2):
        raise ValueError('选中人物关键点坐标域无效')
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def install_face(pipe, pc):
    """Call from load_face. Never substitute the first face or a synthetic face."""
    lm = np.array(pc.landmarks, dtype=np.float32, copy=True)
    signature = landmarks_identity(lm)
    skin = skin_support(pc)
    if skin is not None and skin.shape != (pipe.h, pipe.w):
        raise ValueError('预览人脸语义支持场必须与真实源画幅相同')
    pipe.facial_wrinkle_face = {'landmarks': lm, 'signature': signature,
                               'skin': None if skin is None else skin.copy(), 'backend': pc.backend,
                               'model_identity': getattr(pc, 'semantic_model_sha256', None)}
    clear_layer(pipe)


def clear_layer(pipe):
    pipe.facial_wrinkle_layer = None
    pipe.facial_wrinkle_delta = None
    pipe.facial_wrinkle_local = None
    pipe.facial_wrinkle_tile_key = None


def clear_face(pipe):
    clear_layer(pipe)
    pipe.facial_wrinkle_face = None


def build_preview(pipe, landmarks, *, force=False):
    face = getattr(pipe, 'facial_wrinkle_face', None)
    if face is None or landmarks_identity(landmarks) != face['signature']:
        clear_layer(pipe)
        # No silently guessed face. Selected-person information must arrive via
        # load_face before build_enhance, including after project/device reload.
        if S.active(getattr(pipe, 'enhance_amounts', {})):
            raise ValueError('面部祛纹缺少当前选中人物的语义与关键点绑定')
        return
    if not force and not S.active(getattr(pipe, 'enhance_amounts', {})):
        clear_layer(pipe)
        return
    admit_working_set((pipe.h, pipe.w), landmarks)
    import torch
    window, lm = bounds(landmarks, pipe.h, pipe.w)
    y, x, h, w = window
    source = pipe.repair_base if pipe.repair_base is not None else pipe.src_f32
    pixels = source[0, :, y:y+h, x:x+w].permute(1, 2, 0).to('cpu', torch.float32).numpy()
    skin = None if face['skin'] is None else face['skin'][y:y+h, x:x+w]
    layer = FacialWrinkleLayer(window, pixels, lm, skin, backend=face['backend'], model_identity=face['model_identity'])
    layer.source_version = pipe.repair_version
    pipe.facial_wrinkle_layer = layer


def solve_preview(pipe, amounts):
    checked = S.check(amounts)
    tile_key = getattr(pipe, 'facial_wrinkle_tile_key', None)
    if tile_key is not None:
        if tile_key != tuple(checked[k] for k in S.KEYS):
            raise ValueError('导出分块的面部祛纹强度与冻结全脸修正不一致')
        return
    layer = getattr(pipe, 'facial_wrinkle_layer', None)
    if layer is None:
        if not S.active(amounts): return
        face = getattr(pipe, 'facial_wrinkle_face', None)
        if face is None:
            raise ValueError('面部祛纹还没有绑定当前选中人物，未忽略所请求的效果')
        build_preview(pipe, face['landmarks'], force=True)
        layer = pipe.facial_wrinkle_layer
    delta = layer.solve(amounts)
    attach_delta(pipe, layer.window, delta)
    pipe.enhance_facts.update(layer.facts)


def configure_export(spec, snap, h, w):
    """Set transient fields on ExportSpec; never serialize them into a recipe."""
    spec.facial_wrinkle_skin = None
    spec.facial_wrinkle_backend = None
    spec.facial_wrinkle_model_identity = None
    if not S.active(spec.enhance or {}): return
    pc = snap.get('precompute')
    if pc is None or getattr(pc, 'backend', None) != 'mediapipe':
        raise ValueError('面部祛纹导出需要当前图片选中人物的真实关键点')
    if landmarks_identity(pc.landmarks) != landmarks_identity(spec.landmarks):
        raise ValueError('面部祛纹导出人物与分析结果不匹配，不能按人脸序号猜测')
    skin = skin_support(pc)
    if skin is None:
        raise ValueError('面部祛纹导出缺少可信皮肤支持；不会悄悄省略或整脸处理')
    admit_working_set((h, w), spec.landmarks)
    if skin.shape != (h, w):
        from .third_party.rapidretouch.under_eye import cv2
        if cv2 is None: raise RuntimeError('面部祛纹导出需要 OpenCV')
        skin = cv2.resize(skin, (w, h), interpolation=cv2.INTER_LINEAR)
    spec.facial_wrinkle_skin = np.ascontiguousarray(skin, dtype=np.float32)
    spec.facial_wrinkle_backend = pc.backend
    spec.facial_wrinkle_model_identity = pc.semantic_model_sha256


def prepare_export(spec, source, repaired, divisor):
    if not S.active(spec.enhance or {}): return None
    if getattr(spec, 'facial_wrinkle_backend', None) != 'mediapipe' or getattr(spec, 'facial_wrinkle_skin', None) is None:
        raise ValueError('面部祛纹导出尚未验证人物和皮肤支持')
    h, w = source.shape[:2]
    if spec.facial_wrinkle_skin.shape != (h, w):
        raise ValueError('面部祛纹导出皮肤支持未对齐全尺寸源图')
    admit_working_set((h, w), spec.landmarks)
    window, lm = bounds(spec.landmarks, h, w)
    y, x, rh, rw = window
    pixels = (repaired[y:y+rh, x:x+rw] if repaired is not None else
              source[y:y+rh, x:x+rw].astype(np.float32) / divisor)
    layer = FacialWrinkleLayer(window, pixels, lm, spec.facial_wrinkle_skin[y:y+rh, x:x+rw],
                               backend=spec.facial_wrinkle_backend, model_identity=spec.facial_wrinkle_model_identity)
    layer.solve(spec.enhance)
    return layer


def install_export_tile(pipe, layer, origin, amounts):
    """Call after set_enhance_field but BEFORE set_enhance for every tile."""
    checked = S.check(amounts)
    clear_layer(pipe)
    if layer is None:
        if S.active(checked):
            raise ValueError('导出分块缺少已请求的全脸面部祛纹修正')
        return
    key = tuple(checked[k] for k in S.KEYS)
    if key != layer.key:
        raise ValueError('导出分块参数与已冻结的面部祛纹修正不匹配')
    attach_delta(pipe, layer.window, layer.delta, origin)
    pipe.facial_wrinkle_tile_key = key
    pipe.enhance_facts.update(layer.facts)


def resident_bytes(pipe):
    layer = getattr(pipe, 'facial_wrinkle_layer', None)
    delta = getattr(pipe, 'facial_wrinkle_delta', None)
    face = getattr(pipe, 'facial_wrinkle_face', None)
    return ((layer.resident_bytes() if layer else 0) +
            (delta.numel() * delta.element_size() if delta is not None else 0) +
            (face['landmarks'].nbytes + (face['skin'].nbytes if face['skin'] is not None else 0) if face else 0))


def working_bytes(shape, landmarks=None):
    """Conservative transient estimate for budget admission, not a speed shortcut.

    Includes source/lab/relight temporaries, nine masks, three proposal profiles,
    morphology/Hessian scratch, CPU/GPU delta and full semantic field. No proxy
    substitution if rejected. The caller must combine with other render budgets.
    """
    h, w = shape
    roi_pixels = int(h) * int(w)
    if landmarks is not None:
        window, _ = bounds(landmarks, h, w)
        roi_pixels = window[2] * window[3]
    return roi_pixels * 256 + int(h) * int(w) * 4


def admit_working_set(shape, landmarks, *, additional_bytes=0):
    """Fail explicitly before full-face work rather than quietly downsampling.

    This is admission against remaining process/cgroup memory, not an OOM
    guarantee. Existing higher-level decode/render admission is still required.
    """
    from .cpu_memory_budget import available_estimate
    import resource
    need = working_bytes(shape, landmarks) + int(additional_bytes) + 64 * 1024 * 1024
    available = available_estimate()
    soft, _ = resource.getrlimit(resource.RLIMIT_AS)
    if soft != resource.RLIM_INFINITY:
        import os
        with open('/proc/self/statm', encoding='ascii') as stream:
            virtual = int(stream.read().split()[0]) * os.sysconf('SC_PAGE_SIZE')
        available = min(available, max(0, soft - virtual))
    if need > available:
        raise ValueError(f'面部祛纹全尺寸计算需要约 {need // (1024*1024)} MiB 可用内存；当前预算不足，未降低分辨率或省略效果')
    return need
