# SPDX-License-Identifier: AGPL-3.0-only
"""One frozen full-face source correction; shared by preview and 8/16-bit tiles.

Pinned RapidRetouch supplies Hessian line detection, pore-preserving line lift,
fold/hair rejection and relighting. Region selection and max-overlap are new.
No model download, full-face blur, geometry warp or sequential region relight.
"""
from copy import deepcopy
import hashlib
import numpy as np
from . import facial_wrinkle_state as S
from .facial_wrinkle_geometry import geometry
from .facial_wrinkle_native import merge
from .third_party.rapidretouch import under_eye as E

# Lab-lightness line scales relative to the selected face's widest eye. The
# upstream fine profile is retained. Broad expression folds retain 60% depth;
# these are local conservative choices, NOT claimed PixCake numeric settings.
PROFILES = {
    'fine': (E.WRINKLE_SCALES, E.FOLD_KEEP, (E.LINE_LOW, E.LINE_HIGH)),
    'cheek': (E.WRINKLE_SCALES, E.FOLD_KEEP, (.25, .9)),
    'fold': (E.CREASE_SCALES, .60, (E.LINE_LOW, E.LINE_HIGH)),
}


def _profile(key):
    if key == 'wrinkle_cheek': return 'cheek'
    if key in ('wrinkle_nasolabial_left', 'wrinkle_nasolabial_right', 'wrinkle_marionette'): return 'fold'
    return 'fine'


def bounds(landmarks, h, w):
    """Actual selected normalized landmarks, including legitimate edge clipping.

    Unlike the older eye helper this does not reject a whole face merely because
    one peripheral landmark falls just outside the photograph. The source ROI
    clips to the photo; anatomical + skin boundaries still gate every region.
    """
    points = np.asarray(landmarks, dtype=np.float32)
    if points.shape not in ((478, 2), (478, 3)) or not np.isfinite(points).all():
        raise ValueError('面部祛纹窗口需要真实选中人物的 478 点')
    if np.any(points[:, :2] < -1) or np.any(points[:, :2] > 2):
        raise ValueError('面部祛纹关键点明显不在归一化坐标域')
    lm = points[:, :2] * np.array([w, h], np.float32)
    pad = 2 * max(float(np.linalg.norm(lm[33] - lm[133])), float(np.linalg.norm(lm[263] - lm[362])))
    low = np.maximum(np.floor(lm.min(0) - pad), 0).astype(int)
    high = np.minimum(np.ceil(lm.max(0) + pad) + 1, [w, h]).astype(int)
    x, y = map(int, low); width, height = map(int, high - low)
    if min(width, height) < 4:
        raise ValueError('选中人物没有足够的可见源图范围')
    return (y, x, height, width), np.ascontiguousarray(lm)


class FacialWrinkleLayer:
    def __init__(self, window, pixels, landmarks_px, skin_weight, *, backend, model_identity=None):
        self.window = tuple(window)
        y, x, h, w = self.window
        if any(type(v) is not int for v in self.window) or min(y, x) < 0 or min(h, w) < 4 or h * w > 32_000_000:
            raise ValueError('面部祛纹源窗口无效或超过全尺寸预算')
        source = np.asarray(pixels, np.float32)
        if source.shape != (h, w, 3) or not np.isfinite(source).all() or np.any((source < 0) | (source > 1)):
            raise ValueError('面部祛纹需要未量化的有限 working-sRGB float32 源窗口')
        self.source = np.array(source, dtype=np.float32, order='C', copy=True)
        self.landmarks_px = np.array(landmarks_px, dtype=np.float32, copy=True)
        if self.landmarks_px.shape != (478, 2) or not np.isfinite(self.landmarks_px).all():
            raise ValueError('面部祛纹需要 478 点选中人物几何')
        self.skin_weight = None if skin_weight is None else np.array(skin_weight, dtype=np.float32, order='C', copy=True)
        self.backend = backend
        self.model_identity = model_identity
        digest = lambda array: hashlib.sha256(memoryview(np.ascontiguousarray(array)).cast('B')).hexdigest()
        self.analysis_identity = (digest(self.source), digest(self.landmarks_px),
                                  None if self.skin_weight is None else digest(self.skin_weight),
                                  backend, model_identity)
        self.key = None; self.delta = None; self.facts = {}
        self.masks = None; self.geometry_facts = None; self.scale = None
        self.lab = None; self.proposals = {}
        self.source_version = None
        self.source.setflags(write=False)
        self.landmarks_px.setflags(write=False)
        if self.skin_weight is not None: self.skin_weight.setflags(write=False)

    def _prepare(self):
        if self.masks is not None: return
        y, x, h, w = self.window
        # Synthetic/template landmarks are useful contract fixtures, never
        # eligible product geometry. The caller must pass the actual backend.
        if self.backend != 'mediapipe':
            self.masks = {key: np.zeros((h, w), np.float32) for key in S.KEYS}
            self.geometry_facts = {key: {'geom_px': 0, 'gated_px': 0, 'sides': {},
                                        'reason': 'actual_selected_face_required'} for key in S.KEYS}
            self.scale = 0.
            return
        self.masks, self.geometry_facts, self.scale = geometry(self.landmarks_px - [x, y], (h, w), self.skin_weight)

    def _proposal(self, key):
        name = _profile(key)
        if name not in self.proposals:
            if self.lab is None:
                self.lab = E.cv2.cvtColor(self.source, E.cv2.COLOR_RGB2Lab)
            scales, keep, ramp = PROFILES[name]
            lift = E._wrinkle_lift(np.ascontiguousarray(self.lab[..., 0]),
                                  np.ones(self.source.shape[:2], np.float32), self.scale, scales, keep, ramp)
            if not np.isfinite(lift).all():
                raise ValueError('面部祛纹线检测产生无效值，整层拒绝')
            self.proposals[name] = np.ascontiguousarray(np.maximum(lift, 0), dtype=np.float32)
        return self.proposals[name]

    def solve(self, amounts):
        checked = S.check(amounts)
        # Lock state does not enter the pixel cache key or force inference.
        key = tuple(checked[k] for k in S.KEYS)
        if key == self.key: return self.delta
        if not any(key):
            self.delta, self.key = None, key
            self.facts = {k: {'geom_px': 0, 'gated_px': 0, 'changed_px': 0, 'reason': 'disabled', 'sides': {}} for k in S.KEYS}
            return None
        self._prepare()
        facts = deepcopy(self.geometry_facts)
        combined = np.zeros(self.source.shape[:2], np.float32)
        for k, amount in zip(S.KEYS, key):
            facts[k]['changed_px'] = 0
            if not amount:
                facts[k]['reason'] = 'disabled'
                continue
            if facts[k]['gated_px'] == 0: continue
            proposal = self._proposal(k)
            support = self.masks[k]
            facts[k]['changed_px'] = int(np.count_nonzero(proposal * support * amount > 1e-5))
            if not facts[k]['changed_px']:
                facts[k]['reason'] = 'no_detected_wrinkle_lines'
                continue
            merge(proposal, support, amount, combined)
        combined[combined <= 1e-5] = 0
        delta = None
        if np.any(combined):
            # Only one relight, from one frozen source. Overlaps cannot brighten
            # again by feeding corrected pixels into the next region detector.
            corrected_lab = self.lab.copy()
            E._relight(corrected_lab, combined, self.scale)
            corrected = np.clip(E.cv2.cvtColor(corrected_lab, E.cv2.COLOR_Lab2RGB), 0, 1)
            delta = np.ascontiguousarray(np.where((combined > 0)[..., None], corrected - self.source, 0), dtype=np.float32)
            if not np.isfinite(delta).all():
                raise ValueError('面部祛纹修正产生无效值，未更新缓存')
        self.delta, self.key, self.facts = delta, key, facts
        return delta

    def resident_bytes(self):
        return sum(a.nbytes for a in (self.source, self.skin_weight, self.lab, self.delta,
                   *self.proposals.values(), *(self.masks or {}).values()) if a is not None)


def attach_delta(pipe, window, delta, origin=(0, 0)):
    """Crop an already solved full-face field. NEVER solve inside an export tile."""
    import torch
    pipe.facial_wrinkle_delta = None; pipe.facial_wrinkle_local = None
    if delta is None: return
    y, x, h, w = window
    if delta.shape != (h, w, 3) or not np.isfinite(delta).all():
        raise ValueError('面部祛纹导出场尺寸或像素无效')
    y, x = y - origin[0], x - origin[1]
    y0, x0 = max(0, y), max(0, x)
    y1, x1 = min(pipe.h, y + h), min(pipe.w, x + w)
    if y1 <= y0 or x1 <= x0: return
    crop = np.ascontiguousarray(delta[y0-y:y1-y, x0-x:x1-x])
    pipe.facial_wrinkle_delta = torch.tensor(crop, device=pipe.device).permute(2, 0, 1)[None]
    pipe.facial_wrinkle_local = (y0, x0, y1-y0, x1-x0)


def apply_delta(pipe, pixels):
    """Call BEFORE automatic deform; recovery receives this operator's I/O only."""
    delta = getattr(pipe, 'facial_wrinkle_delta', None)
    if delta is None: return pixels
    import torch
    y, x, h, w = pipe.facial_wrinkle_local
    output = pixels.clone()
    source = pixels[:, :, y:y+h, x:x+w]
    output[:, :, y:y+h, x:x+w] = torch.where(delta != 0, (source + delta).clamp(0, 1), source)
    return output


def refresh_source(pipe):
    """Repair changes invalidate correction; same source is never cumulatively edited."""
    layer = getattr(pipe, 'facial_wrinkle_layer', None)
    if layer is None or layer.source_version == pipe.repair_version: return
    import torch
    y, x, h, w = layer.window
    source = pipe.repair_base if pipe.repair_base is not None else pipe.src_f32
    pixels = source[0, :, y:y+h, x:x+w].permute(1, 2, 0).to('cpu', torch.float32).numpy()
    replacement = FacialWrinkleLayer(layer.window, pixels, layer.landmarks_px, layer.skin_weight, backend=layer.backend, model_identity=layer.model_identity)
    replacement.source_version = pipe.repair_version
    replacement.solve(pipe.enhance_amounts)
    attach_delta(pipe, replacement.window, replacement.delta)
    pipe.facial_wrinkle_layer = replacement
    pipe.enhance_facts.update(replacement.facts)
