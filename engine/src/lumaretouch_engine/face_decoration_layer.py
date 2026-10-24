# SPDX-License-Identifier: GPL-3.0-or-later
"""One frozen source-resolution contribution, cropped unchanged for export tiles."""
import numpy as np
from . import face_decoration_state as S, people_state as P
from .face_decoration_catalogue import CATALOGUE_SHA256
from .face_decoration_geometry import fields, mask, FACE_OVAL, MAX_PIXELS
from .face_decoration_native import delta as native_delta
from .lip_makeup_runtime import identity


def bounds(landmarks, h, w):
    identity(landmarks)
    lm = np.asarray(landmarks, dtype=np.float32)[:, :2] * np.array([w, h], dtype=np.float32)
    oval = lm[list(FACE_OVAL)]
    x, y = np.maximum(np.floor(oval.min(axis=0) - 4), 0).astype(int)
    x1, y1 = np.minimum(np.ceil(oval.max(axis=0) + 4), [w, h]).astype(int)
    window = (int(y), int(x), int(y1 - y), int(x1 - x))
    if min(window[2:]) < 4 or window[2] * window[3] > MAX_PIXELS:
        raise ValueError('面部装饰原始尺寸窗口无效或超预算；未缩小人物')
    return window, lm


def admit_working_set(window):
    """Conservative transient-array budget, not a measured peak or a QA result."""
    from .cpu_memory_budget import available_estimate
    import os
    import resource
    need = window[2] * window[3] * 256 + 64 * 1024 * 1024
    available = available_estimate()
    soft, _ = resource.getrlimit(resource.RLIMIT_AS)
    if soft != resource.RLIM_INFINITY:
        with open('/proc/self/statm', encoding='ascii') as stream:
            virtual = int(stream.read().split()[0]) * os.sysconf('SC_PAGE_SIZE')
        available = min(available, max(0, soft - virtual))
    if need > available:
        raise ValueError(f'面部装饰原始尺寸计算需要约 {need // (1024 * 1024)} MiB 可用内存；未降采样或省略')
    return need


class FaceDecorationLayer:
    def __init__(self, window, source, landmarks, skin, excluded, *, backend, face_ref, semantic_sha, reviewed):
        if (type(window) not in (tuple, list) or len(window) != 4
                or any(type(v) is not int for v in window) or min(window[:2]) < 0
                or min(window[2:]) < 4 or window[2] * window[3] > MAX_PIXELS):
            raise ValueError('面部装饰源窗口无效或超出预算')
        self.window = tuple(window)
        y, x, h, w = self.window
        self.face_ref = P.check_ref(face_ref)
        P.digest(semantic_sha)
        if (type(source) is not np.ndarray or source.dtype != np.float32 or source.shape != (h, w, 3)
                or not np.isfinite(source).all() or np.any((source < 0) | (source > 1))):
            raise ValueError('面部装饰需要未量化 SDR working-sRGB float32 修复源')
        mask(skin, (h, w), '皮肤审核'); mask(excluded, (h, w), '排除场')
        mask(reviewed, (h, w), '独立装饰可见皮肤审核')
        self.source = np.array(source, copy=True, order='C')
        self.landmarks = np.asarray(landmarks, dtype=np.float32).copy() - np.array([x, y], np.float32)
        self.skin = np.array(skin, copy=True, order='C')
        self.excluded = np.array(excluded, copy=True, order='C')
        self.reviewed = np.array(reviewed, copy=True, order='C')
        self.backend = backend
        self.semantic_sha = semantic_sha
        self.key = self.delta = self.frame = self.support = None
        self.facts = {}
        for array in (self.source, self.landmarks, self.skin, self.excluded, self.reviewed):
            array.setflags(write=False)

    def solve(self, recipe):
        recipe = S.check(recipe)
        key = (recipe['pattern'], recipe['strength'], CATALOGUE_SHA256)
        if self.key == key:
            return self.delta
        if not S.active(recipe):
            self.key, self.delta = key, None
            self.facts = {'reason': 'disabled', 'changed_pixels': 0}
            return None
        if self.frame is None:
            self.frame, self.support, self.geometry_facts = fields(
                self.landmarks, self.source.shape[:2], self.skin, self.excluded,
                backend=self.backend, reviewed=self.reviewed)
            self.frame.setflags(write=False); self.support.setflags(write=False)
        result = native_delta(self.source, self.frame, self.support, recipe)
        if not np.isfinite(result).all() or np.any((self.source + result < 0) | (self.source + result > 1)):
            raise ValueError('面部装饰输出非有限或越界；未发布')
        result.setflags(write=False)
        changed = int(np.count_nonzero(np.any(result != 0, axis=2)))
        self.facts = {
            **self.geometry_facts, 'face_ref': dict(self.face_ref), 'recipe': recipe,
            'catalogue_sha256': CATALOGUE_SHA256, 'semantic_model_sha256': self.semantic_sha,
            'changed_pixels': changed, 'reason': None if changed else 'no_measurable_change',
            'rasterizer': 'exact-source-pixel-area-piecewise-linear-pigment-v1',
            'contribution_model': 'bounded-multiplicative-pigment-not-blemish-removal',
            'composition': 'direction-preserving-per-pixel-SDR-headroom-gain-no-channel-clipping',
        }
        self.key, self.delta = key, result
        return result

    def resident_bytes(self):
        return sum(a.nbytes for a in (self.source, self.landmarks, self.skin, self.excluded, self.reviewed,
                                      self.frame, self.support, self.delta) if a is not None)


def prepare_record(face_ref, landmarks, recipe, source, *, excluded, skin, backend, semantic_sha, reviewed=None):
    recipe = S.check(recipe)
    if not S.active(recipe):
        return None  # Exact neutral requires no geometry, review, semantic or native availability.
    from .people_effects import LocalEffect
    ref = P.check_ref(face_ref)
    P.digest(semantic_sha)
    if type(source) is not np.ndarray or source.ndim != 3 or source.shape[2] != 3:
        raise ValueError('面部装饰源图无效')
    h, w = source.shape[:2]
    window, lm = bounds(landmarks, h, w)
    admit_working_set(window)
    # Validate evidence before multiplication, so malformed out-of-range fields
    # cannot cancel each other into superficially valid coverage.
    mask(skin, (h, w), '皮肤证据'); mask(excluded, (h, w), '遮挡与其他人物排除场')
    mask(reviewed, (h, w), '独立装饰可见皮肤审核，请先手绘并确认')
    y, x, rh, rw = window
    layer = FaceDecorationLayer(window, source[y:y+rh, x:x+rw], lm, skin[y:y+rh, x:x+rw],
                                excluded[y:y+rh, x:x+rw], backend=backend,
                                face_ref=ref, semantic_sha=semantic_sha, reviewed=reviewed[y:y+rh, x:x+rw])
    result = layer.solve(recipe)
    return LocalEffect(ref, 'face_decoration', window, delta=result, facts=layer.facts)
