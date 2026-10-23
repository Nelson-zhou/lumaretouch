"""Float-pixel operator-local attenuation shared by preview and tiled export.

before/after must be this operator's input/output, NOT the immutable source.
Recovery never changes the stage order or restores a whole unedited photograph.
"""
import numpy as np
from . import effect_recovery_state as S
from .optional_dependencies import optional_module


def check_fields(fields, shape=None, *, state=None):
    if type(fields) is not list or len(fields) > len(S.TARGETS):
        raise ValueError('效果恢复场列表无效')
    checked, seen, pixels = [], set(), 0
    for item in fields:
        if type(item) is not dict or set(item) != {'target', 'weight'}:
            raise ValueError('效果恢复场缺少目标或覆盖度')
        name = S.target(item['target'])
        weight = item['weight']
        if name in seen or (type(weight) is not np.ndarray or weight.dtype != np.uint8
                or weight.ndim != 2 or min(weight.shape) < 1
                or shape is not None and tuple(shape) != weight.shape):
            raise ValueError('效果恢复场重复、尺寸或像素类型无效')
        pixels += weight.size
        seen.add(name)
        checked.append({'target': name, 'weight': weight})
    if pixels > S.MAX_MASK_PIXELS:
        raise ValueError('效果恢复场超过总像素预算')
    if state is not None and seen != {row['target'] for row in S.enabled(state)}:
        raise ValueError('已启用的效果恢复蒙版缺失；不能导出未恢复的效果')
    return checked


class EffectRecoveryStage:
    def __init__(self, device, shape):
        self.device, self.shape = device, tuple(shape)
        self.fields = {}
        self.suspended = None
        self.suspended_targets = {}
        self.required = set()

    def set(self, fields, *, state=None, reason=None):
        self.suspended_targets = {}
        if reason is not None:
            if type(reason) is not str or not reason or fields or state is None:
                raise ValueError('挂起效果恢复必须保留目标配方和可见原因')
            self.fields = {}
            self.required = {r['target'] for r in S.enabled(state)}
            self.suspended = reason
            return
        checked = check_fields(fields, self.shape, state=state)
        torch = optional_module('torch')
        owned = {item['target']: torch.tensor(item['weight'], dtype=torch.uint8,
                    device=self.device)[None, None] for item in checked}
        self.fields, self.required, self.suspended = owned, set(owned), None

    def apply(self, target, before, after, *, align=None):
        S.target(target)
        if target not in self.required:
            return after
        if self.suspended or target in self.suspended_targets:
            # Fail closed: suspend only this operator, with the reason exposed
            # in doc_state. Ignoring a lost recovery mask would restore an
            # unwanted automatic effect. Export never permits this branch.
            return before
        coverage = self.fields.get(target)
        if coverage is None:
            raise ValueError('效果恢复覆盖度丢失，拒绝忽略用户笔迹')
        if before.shape != after.shape or tuple(after.shape[-2:]) != self.shape:
            raise ValueError('效果恢复输入与算子输出不在同一像素域')
        torch = optional_module('torch')
        weight = coverage.to(dtype=after.dtype).div(255.0)
        if target in ('background_replace', 'id_background'):
            if align is None:
                raise ValueError('换底恢复需要真实形变场，不接受原图坐标直接贴到形变图')
            weight = align(weight)
        elif align is not None:
            raise ValueError('形变前恢复目标不能重复形变蒙版')
        if not torch.isfinite(before).all() or not torch.isfinite(after).all():
            raise ValueError('效果恢复输入含非有限像素')
        # Exact endpoints keep untouched pixels and complete recovery bit-for-bit.
        # Float32 source/export pixels never travel through a uint8 image buffer.
        mixed = after + (before - after) * weight
        return torch.where(weight <= 0, after, torch.where(weight >= 1, before, mixed))

    def resident_bytes(self):
        return sum(int(field.numel() * field.element_size()) for field in self.fields.values())
