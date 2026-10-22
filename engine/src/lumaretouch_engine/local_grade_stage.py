"""Ordered retained local grades at the existing post-LUT grade position.

Keep each group's mask separate: an intersection/subtraction belongs to its
own adjustment, not a merged mask. Coverage is retained as uint8 on the render
device, and only one group's float coverage is materialized/warped at a time.
RGB is never quantized here. The rasterizer and its limits remain in Rust LMR2.
"""
import re
import time
import numpy as np

from .optional_dependencies import optional_module
from .local_grade_layers import MAX_LAYERS, MAX_MASK_PIXELS, grade
from .ops.grade import grade_t
from .ops.guided import mix_masked

torch = optional_module('torch')


def check_fields(fields, shape=None, *, groups=None):
    """Validate all coverage before copying; never interpret absent as global."""
    if type(fields) is not list or len(fields) > MAX_LAYERS:
        raise ValueError('Independent grade fields exceed the eight-group budget')
    checked, seen, pixels = [], set(), 0
    for item in fields:
        if type(item) is not dict or set(item) != {'id', 'grade', 'weight'}:
            raise ValueError('Independent grade field is missing its mask or parameters')
        ident = item['id']
        if (type(ident) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', ident)
                or ident in seen):
            raise ValueError('Invalid or duplicate independent grade field ID')
        seen.add(ident)
        values = grade(item['grade'])
        weight = item['weight']
        if (type(weight) is not np.ndarray or weight.dtype != np.uint8
                or weight.ndim != 2 or min(weight.shape) < 1
                or (shape is not None and weight.shape != tuple(shape))):
            raise ValueError('Independent grade coverage must be source-grid (H,W) uint8')
        pixels += int(weight.size)
        if pixels > MAX_MASK_PIXELS:
            raise ValueError('Independent grade coverage exceeds 128M retained pixels')
        checked.append({'id': ident, 'grade': values, 'weight': weight})
    if groups is not None:
        from .local_grade_layers import check
        expected = [layer for layer in check(groups)['layers'] if layer['enabled']]
        if (len(expected) != len(checked) or any(
                layer['id'] != field['id'] or layer['grade'] != field['grade']
                for layer, field in zip(expected, checked))):
            raise ValueError('An enabled independent grade mask is missing, stale or reordered')
    return checked


class LocalGradeStage:
    def __init__(self, device, shape):
        self.device, self.shape = device, tuple(shape)
        self.fields = []
        self.suspended = None
        self.last_ms = 0.0

    def set(self, fields, *, reason=None):
        if reason is not None and (type(reason) is not str or fields):
            raise ValueError('A suspended local grade stage cannot retain active fields')
        checked = check_fields(fields, self.shape)
        # Validate first; replacement temporarily owns old+new uint8 weights.
        # At the hard pixel limit this is <=256 MB of mask payload, not a total
        # process/VRAM guarantee. No hidden permanent float copy is retained.
        owned = [(item['id'], tuple(item['grade']),
                  torch.tensor(item['weight'], dtype=torch.uint8, device=self.device)[None, None])
                 for item in checked]
        self.fields, self.suspended = owned, reason
        self.last_ms = 0.0

    def apply(self, pixels, align_source_mask):
        self.last_ms = 0.0
        if self.suspended or not self.fields:
            return pixels
        started = time.perf_counter()
        out = pixels
        for _, values, coverage in self.fields:
            dh, ds, dv, amount = values
            if amount == 0 or not (dh or ds or dv):
                continue
            # This is the exact deformation grid and unchanged-pixel/border
            # policy already used by the image, including the RGB16 path.
            weight = align_source_mask(coverage.to(dtype=pixels.dtype).div_(255.0))
            graded = grade_t(out, dh, ds, dv, amount=amount)
            if not torch.isfinite(graded).all():
                raise ValueError('Independent local grade produced nonfinite pixels')
            out = mix_masked(out, graded, 1.0, weight)
            del graded, weight
        if self.device.type != 'cpu':
            torch.cuda.synchronize(self.device)
        self.last_ms = (time.perf_counter() - started) * 1000.0
        return out

    def set_parameters(self, groups):
        """Scalar-only update after the runtime verified identical mask inputs."""
        from .local_grade_layers import check
        enabled = [layer for layer in check(groups)['layers'] if layer['enabled']]
        if self.suspended or [layer['id'] for layer in enabled] != [row[0] for row in self.fields]:
            raise ValueError('Cannot update grade parameters without the exact retained masks')
        self.fields = [(ident, tuple(layer['grade']), weight)
                       for layer, (ident, _, weight) in zip(enabled, self.fields)]

    def resident_bytes(self):
        return sum(int(weight.numel() * weight.element_size()) for _, _, weight in self.fields)
