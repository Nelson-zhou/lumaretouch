# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply measured reference to current source-stage pixels before the ONE warp."""
import numpy as np
from . import hair_unification_state as S, hair_unification_native as N
from .hair_unification_runtime import Parameters


def apply_records_np(current, records, recovery=None, *, source_shape=None, origin=(0, 0), cancelled=lambda: False):
    selected = [record for record in records if record.stage == S.STAGE]
    if not selected:
        return current, {'stage': S.STAGE, 'changed_pixels': 0, 'overlap_pixels': 0}
    if (type(current) is not np.ndarray or current.dtype != np.float32 or current.ndim != 3
            or current.shape[2] != 3 or not np.isfinite(current).all() or np.any((current < 0) | (current > 1))):
        raise ValueError('Hair-unification composition requires actual current SDR float32 RGB')
    oy, ox = origin; h, w = current.shape[:2]
    source_shape = tuple(current.shape[:2]) if source_shape is None else tuple(source_shape)
    if (any(type(v) is not int for v in (oy, ox, *source_shape)) or min(oy, ox) < 0
            or oy+h > source_shape[0] or ox+w > source_shape[1]):
        raise ValueError('Hair-unification tile differs from source dimensions')
    from .cpu_memory_budget import available_estimate
    if available_estimate() < h*w*36 + 32*1024*1024:
        raise MemoryError('Hair-unification current-stage composition exceeds memory admission')
    result = current; occupied = np.zeros((h, w), bool)
    for record in selected:
        if (recovery or {}).get((record.face_ref['face_instance_id'], S.STAGE)) is not None:
            raise ValueError('Hair unification cannot borrow another operator recovery mask')
        if not isinstance(record.amounts, Parameters): raise ValueError('Missing measured hair-unification parameters')
        ref = record.amounts.reference.checked()
        if (ref.source_height, ref.source_width) != source_shape:
            raise ValueError('Hair-unification reference was measured at another source extent')
        y, x, rh, rw = record.window; weights = record.weights
        if (min(y, x) < 0 or min(rh, rw) <= 0 or y+rh > source_shape[0] or x+rw > source_shape[1]
                or type(weights) is not np.ndarray or weights.dtype != np.float32 or weights.shape != (rh, rw)
                or not np.isfinite(weights).all() or np.any((weights < 0) | (weights > 1))):
            raise ValueError('Hair-unification target coverage has invalid source ownership')
        y0, x0 = max(y, oy), max(x, ox); y1, x1 = min(y+rh, oy+h), min(x+rw, ox+w)
        if y1 <= y0 or x1 <= x0: continue
        coverage = weights[y0-y:y1-y, x0-x:x1-x]
        used = occupied[y0-oy:y1-oy, x0-ox:x1-ox]
        if np.any((coverage > 0) & used): raise ValueError('Hair-unification target ownership overlaps')
        used |= coverage > 0
        # Native private staging is capped at 262144 pixels; never remeasure a
        # reference here, and every tile receives exact source-space coordinates.
        rows = max(1, N.MAX_TILE_PIXELS // (x1-x0))
        for top in range(y0, y1, rows):
            bottom = min(top+rows, y1)
            cov = np.ascontiguousarray(weights[top-y:bottom-y, x0-x:x1-x])
            if not np.any(cov > 0): continue
            pixels = np.ascontiguousarray(current[top-oy:bottom-oy, x0-ox:x1-ox])
            updated = N.compose(pixels, cov, ref, record.amounts.recipe, origin=(x0, top), cancelled=cancelled)
            if result is current: result = current.copy()
            destination = result[top-oy:bottom-oy, x0-ox:x1-ox]
            take = cov > 0
            destination[take] = updated[take]
    return result, {'stage': S.STAGE, 'changed_pixels': int(np.count_nonzero(np.any(result != current, axis=2))),
                    'overlap_pixels': 0, 'composition': 'current-linear-luminance-preserving-chroma'}


def apply_records_t(pixels, records, recovery=None, *, source_shape, origin=(0, 0), cancelled=lambda: False):
    selected = tuple(record for record in records if record.stage == S.STAGE)
    if not selected: return pixels
    import torch
    if (not isinstance(pixels, torch.Tensor) or pixels.dtype != torch.float32 or pixels.ndim != 4
            or pixels.shape[0] != 1 or pixels.shape[1] != 3):
        raise ValueError('Hair-unification tensor needs current float32 NCHW RGB')
    # CPU Rust is the sole composer, including GPU previews; no unverified
    # duplicate shader algorithm. Copyback is private until all tiles succeed.
    from .cpu_memory_budget import available_estimate
    if available_estimate() < pixels.shape[2]*pixels.shape[3]*48 + 32*1024*1024:
        raise MemoryError('Hair-unification tensor transfer exceeds CPU memory admission')
    current = np.array(pixels[0].permute(1, 2, 0).detach().to('cpu').numpy(), dtype=np.float32, order='C', copy=True)
    result, _ = apply_records_np(current, selected, recovery, source_shape=source_shape, origin=origin, cancelled=cancelled)
    if result is current: return pixels
    return torch.from_numpy(result).permute(2, 0, 1)[None].to(device=pixels.device, dtype=pixels.dtype)


def apply_source(pipe, pixels):
    prepared = getattr(pipe, 'people_prepared', None)
    if prepared is None: raise ValueError('Canonical people preparation is unavailable')
    return apply_records_t(pixels, prepared.effects, prepared.recovery,
                           source_shape=prepared.geometry.delta.shape[1:3], origin=pipe.people_origin)
