"""Source-derived under-eye and eye-detail correction, shared by preview and tiled export.

A complete face ROI is solved before cropping into export tiles: reference skin
and crease filters must never see tile edges. Existing eye/teeth masks stay 3-D.
"""
from __future__ import annotations
import numpy as np
from .ops import enhance as ENH
from .third_party.rapidretouch import under_eye as EYES
from .third_party.rapidretouch import eye_detail as DETAIL
from . import red_eye_apply as RED_EYE
from . import sclera_purify_apply as PURIFY

KEYS = ("dark_circles", "eye_bags", "veins", "catchlight_left", "catchlight_right", "sclera_purify", "red_eye")

def correct(source, landmarks, key, *, cancelled=lambda: False, red_eye_result=None, purify_result=None):
    faces = [landmarks.astype(np.float32)]
    amounts = dict(zip(KEYS,key))
    out = source
    occupied = None
    # Both new consumers measure the untouched source. Their geometric supports
    # exclude one another; neither can borrow the other's altered reference.
    for module,prepared,name in ((RED_EYE,red_eye_result,'red_eye'),(PURIFY,purify_result,'sclera_purify')):
        if not amounts.get(name,0):continue
        result = prepared if prepared is not None else module.correct(source,landmarks,amounts[name],cancelled=cancelled)
        delta = result[0]-source
        changed = np.any(delta!=0,axis=2)
        if occupied is not None and np.any(occupied & changed):
            raise ENH.EnhanceError('祛红眼与眼白净化的源支持重叠，拒绝重复修正')
        occupied = changed if occupied is None else occupied|changed
        out = np.where(delta!=0,out+delta,out)
    if any(key[:2]):
        out = EYES.apply(out, faces, EYES.Params(*key[:2]))
    if any(key[2:5]):
        out = DETAIL.apply(out, faces, amounts)
    return out


def bounds(landmarks, h, w):
    lm = ENH._landmark_pixels(landmarks, h, w).astype(np.float32)
    pad = max(np.linalg.norm(lm[33] - lm[133]), np.linalg.norm(lm[263] - lm[362])) * 2
    x0, y0 = np.maximum(np.floor(lm.min(0) - pad), 0).astype(int)
    x1, y1 = np.minimum(np.ceil(lm.max(0) + pad) + 1, [w, h]).astype(int)
    return (int(y0), int(x0), int(y1-y0), int(x1-x0)), lm


class UnderEyeLayer:
    def __init__(self, window, pixels, landmarks_px):
        self.window = window
        y, x, h, w = window
        self.source = np.ascontiguousarray(pixels, dtype=np.float32).copy()
        self.landmarks = (landmarks_px - [x, y]) / [w, h]
        self.key = None
        self.delta = None
        self.facts = {}

    def solve(self, amounts, *, cancelled=lambda: False):
        key = tuple(float(amounts.get(k, 0)) for k in KEYS)
        if key == self.key:
            return self.delta
        if not any(key):
            self.delta = None
            self.key = key
            self.facts = {k: {"gated_px": 0, "geom_px": 0, "reason": "disabled"} for k in KEYS}
            return None
        if any(key[:5]) and EYES.cv2 is None:
            raise ENH.EnhanceError("眼部局部修正需要 OpenCV；未生成替代效果")
        named = dict(zip(KEYS,key))
        if named['sclera_purify']:
            from .cpu_memory_budget import available_estimate
            # Additional full-face private results/composition arrays, beyond
            # the already owned source; native per-eye scratch is admitted again.
            extra = (7 if named['red_eye'] else 5)*self.source.nbytes + 4*self.source.shape[0]*self.source.shape[1]
            if extra > available_estimate():
                raise MemoryError('眼白净化源图私有缓冲预算不足；不降为代理图或发布半层')
        red_result = RED_EYE.correct(self.source,self.landmarks,named['red_eye'],cancelled=cancelled) if named['red_eye'] else None
        purify_result = PURIFY.correct(self.source,self.landmarks,named['sclera_purify'],cancelled=cancelled) if named['sclera_purify'] else None
        corrected = correct(self.source,self.landmarks,key,cancelled=cancelled,red_eye_result=red_result,purify_result=purify_result)
        delta = np.ascontiguousarray(corrected - self.source)
        if not np.isfinite(delta).all():
            raise ENH.EnhanceError("眼部局部修正产生非有限值，整层拒绝")
        facts = {}
        # Each enabled control gets its own measured support, never inferred from another slider.
        for i, k in enumerate(KEYS):
            if not key[i]:
                facts[k] = {"gated_px": 0, "geom_px": 0, "reason": "disabled"}
                continue
            if k == "red_eye":
                facts[k] = red_result[1]
                continue
            if k == "sclera_purify":
                facts[k] = purify_result[1]
                continue
            single = [0.0] * len(KEYS)
            single[i] = key[i]
            one = corrected if sum(v != 0 for v in key) == 1 and key[i] else correct(self.source, self.landmarks, single, cancelled=cancelled)
            count = int(np.count_nonzero(np.max(np.abs(one - self.source), axis=2) > 1e-7))
            facts[k] = {"gated_px": count, "geom_px": count,
                             "reason": None if count else ("disabled" if not key[i] else "no_eligible_eye_pixels")}
        self.delta, self.key, self.facts = delta, key, facts
        return delta


def attach_delta(pipe, window, delta, origin=(0, 0)):
    import torch
    pipe.under_eye_delta = None
    pipe.under_eye_local = None
    if delta is None:
        return
    y, x, h, w = window
    y, x = y - origin[0], x - origin[1]
    y0, x0 = max(0, y), max(0, x)
    y1, x1 = min(pipe.h, y+h), min(pipe.w, x+w)
    if y1 <= y0 or x1 <= x0:
        return
    cropped = np.ascontiguousarray(delta[y0-y:y1-y, x0-x:x1-x])
    pipe.under_eye_delta = torch.as_tensor(cropped, device=pipe.device).permute(2, 0, 1)[None]
    pipe.under_eye_local = (y0, x0, y1-y0, x1-x0)


def apply_delta(pipe, t):
    if pipe.under_eye_delta is None:
        return t
    y, x, h, w = pipe.under_eye_local
    out = t.clone()
    sub = out[:, :, y:y+h, x:x+w]
    import torch
    out[:, :, y:y+h, x:x+w] = torch.where(pipe.under_eye_delta != 0,
        (sub + pipe.under_eye_delta).clamp(0, 1), sub)
    return out


def refresh_source(pipe):
    """Repair edits invalidate the source-derived correction, not its landmarks."""
    layer = pipe.under_eye_layer
    if layer is None or getattr(layer, "source_version", None) == pipe.repair_version:
        return
    import torch
    y, x, h, w = layer.window
    source = pipe.repair_base if pipe.repair_base is not None else pipe.src_f32
    pixels = source[0, :, y:y+h, x:x+w].permute(1, 2, 0).to("cpu", torch.float32).numpy()
    replacement = UnderEyeLayer(layer.window, pixels, layer.landmarks * [w, h] + [x, y])
    delta = replacement.solve(pipe.enhance_amounts, cancelled=getattr(pipe,"teeth_colour_cancelled",lambda:False))
    replacement.source_version = pipe.repair_version
    attach_delta(pipe, replacement.window, delta)
    pipe.under_eye_layer = replacement
    pipe.enhance_facts.update(replacement.facts)
