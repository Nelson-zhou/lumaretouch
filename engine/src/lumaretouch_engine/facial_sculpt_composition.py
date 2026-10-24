# SPDX-License-Identifier: GPL-3.0-or-later
"""Pointwise current-stage composition of an immutable SOURCE log-gain field.

Fine texture is never replaced by either low-pass base. Only a slowly varying
common linear-light gain is applied; at fixed gain linear RGB ratios survive.
This is not a guarantee that microcontrast is invariant at field boundaries.
"""
import numpy as np
BOUND = .2400001


def apply_np(current, log_gain):
    if (type(current) is not np.ndarray or type(log_gain) is not np.ndarray
            or current.dtype != np.float32 or log_gain.dtype != np.float32 or current.ndim != 3
            or current.shape[-1] != 3 or log_gain.shape != current.shape[:2]):
        raise ValueError('Facial structure composition requires aligned float32 RGB/HW field')
    if not np.isfinite(log_gain).all() or np.any(np.abs(log_gain) > BOUND):
        raise ValueError('Facial structure log gain exceeds its source bound')
    if not np.any(log_gain != 0):
        return current
    if not np.isfinite(current).all() or np.any((current < 0) | (current > 1)):
        raise ValueError('Active facial structure refuses HDR/nonfinite pixels, never clips')
    encoded = current.astype(np.float64)
    linear = np.where(encoded <= .04045, encoded/12.92, ((encoded+.055)/1.055)**2.4)
    requested = np.exp(log_gain.astype(np.float64))[..., None]
    peak = np.max(linear, axis=2, keepdims=True)
    feasible = np.minimum(requested, 1/np.where(peak > 0, peak, 1))
    gain = np.where(feasible < requested, feasible*(1-1e-12), feasible)
    result = linear*gain
    if not np.isfinite(result).all() or np.any((result < 0) | (result > 1)):
        raise ValueError('Facial structure common gain failed; no channel clipping fallback')
    out = np.where(result <= .0031308, 12.92*result, 1.055*result**(1/2.4)-.055).astype(np.float32)
    untouched = (log_gain == 0) | np.all(current == 0, axis=2) | (gain[..., 0] == 1)
    return np.where(untouched[..., None], current, out)


def apply_records_np(current, records, recovery=None):
    selected = sorted((r for r in records if r.stage == 'facial_sculpt'), key=lambda r: r.face_ref['face_instance_id'])
    if not selected:
        return current, {'stage': 'facial_sculpt', 'overlap_pixels': 0, 'changed_pixels': 0}
    if type(current) is not np.ndarray or current.ndim != 3 or current.shape[-1] != 3:
        raise ValueError('Facial structure requires current HWC RGB')
    h, w = current.shape[:2]
    merged = np.zeros((h, w), np.float32); occupied = np.zeros((h, w), bool); overlap = 0
    from .people_state import check_ref
    for record in selected:
        check_ref(record.face_ref)
        if (type(record.window) not in (tuple, list) or len(record.window) != 4
                or any(type(v) is not int for v in record.window)):
            raise ValueError('Facial structure field window is malformed')
        if (recovery or {}).get((record.face_ref['face_instance_id'], 'facial_sculpt')) is not None:
            raise ValueError('Facial structure has no dedicated recovery contract; use independent visibility review')
        y, x, rh, rw = record.window; field = record.log_gain
        if (min(y, x) < 0 or min(rh, rw) < 1 or y+rh > h or x+rw > w
                or type(field) is not np.ndarray or field.dtype != np.float32 or field.shape != (rh, rw)
                or field.flags.writeable or not field.flags.c_contiguous
                or record.delta is not None or record.chroma_shift is not None or record.weights is not None
                or not np.isfinite(field).all() or np.any(np.abs(field) > BOUND)):
            raise ValueError('Facial structure field differs from its frozen source frame')
        active = field != 0; used = occupied[y:y+rh, x:x+rw]
        overlap += int(np.count_nonzero(active & used)); take = active & ~used
        merged[y:y+rh, x:x+rw][take] = field[take]; used[take] = True
    out = apply_np(current, merged)
    return out, {'stage': 'facial_sculpt', 'overlap_pixels': overlap,
                 'changed_pixels': int(np.count_nonzero(np.any(out != current, axis=2))),
                 'composition': 'source-log-gain-common-linear-rgb-gamut-bound'}


def _chunk_t(current, field):
    import torch
    if not bool(torch.isfinite(current).all()) or bool(((current < 0) | (current > 1)).any()):
        raise ValueError('Active facial structure refuses HDR/nonfinite device pixels')
    encoded = current.to(torch.float64)
    linear = torch.where(encoded <= .04045, encoded/12.92, ((encoded+.055)/1.055).pow(2.4))
    requested = field.to(torch.float64).exp()
    peak = linear.amax(dim=1, keepdim=True)
    feasible = torch.minimum(requested, 1/torch.where(peak > 0, peak, torch.ones_like(peak)))
    gain = torch.where(feasible < requested, feasible*(1-1e-12), feasible)
    result = linear*gain
    if not bool(torch.isfinite(result).all()) or bool(((result < 0) | (result > 1)).any()):
        raise ValueError('Facial structure device common gain failed; no clipping fallback')
    encoded_out = torch.where(result <= .0031308, 12.92*result, 1.055*result.pow(1/2.4)-.055)
    untouched = field.eq(0) | current.eq(0).all(dim=1, keepdim=True) | gain.eq(1)
    return torch.where(untouched, current, encoded_out.to(torch.float32))


def apply_t(current, log_gain):
    import torch
    if (not isinstance(current, torch.Tensor) or not isinstance(log_gain, torch.Tensor)
            or current.dtype != torch.float32 or log_gain.dtype != torch.float32
            or current.ndim != 4 or current.shape[:2] != (1, 3)
            or log_gain.shape != (1, 1, *current.shape[2:]) or log_gain.device != current.device):
        raise ValueError('Facial structure requires aligned float32 1x3xHxW / 1x1xHxW tensors')
    if not bool(torch.isfinite(log_gain).all()) or bool((log_gain.abs() > BOUND).any()):
        raise ValueError('Facial structure device field exceeds source bound')
    if not bool(log_gain.ne(0).any()):
        return current
    width = current.shape[3]
    if not 1 <= width <= 65536 or current.shape[2] < 1:
        raise ValueError('Facial structure tensor extent unsupported')
    rows = max(1, 131072//width)
    output = torch.empty_like(current)
    for y in range(0, current.shape[2], rows):
        output[:, :, y:y+rows] = _chunk_t(current[:, :, y:y+rows], log_gain[:, :, y:y+rows])
    return output


def apply_records_t(pixels, records, recovery=None, *, source_shape, origin=(0, 0)):
    """Crop frozen source fields at exact (y,x) origin; never re-estimate a tile.

    Same lexical FaceRef partition as apply_records_np. No gain accumulation or
    double enhancement on overlap. Complete fields are validated before output.
    """
    selected = sorted((r for r in records if r.stage == 'facial_sculpt'), key=lambda r: r.face_ref['face_instance_id'])
    if not selected:
        return pixels
    import torch
    from .people_state import check_ref
    if (not isinstance(pixels, torch.Tensor) or pixels.dtype != torch.float32
            or pixels.ndim != 4 or pixels.shape[:2] != (1, 3)):
        raise ValueError('Facial structure needs float32 NCHW RGB, not alpha')
    if (type(source_shape) not in (tuple, list) or len(source_shape) != 2
            or any(type(n) is not int or not 1 <= n <= 65536 for n in source_shape)
            or type(origin) not in (tuple, list) or len(origin) != 2
            or any(type(n) is not int or n < 0 for n in origin)):
        raise ValueError('Facial structure needs its exact source extent and tile origin')
    h, w = pixels.shape[2:]; oy, ox = origin
    if min(h, w) < 1 or oy+h > source_shape[0] or ox+w > source_shape[1]:
        raise ValueError('Facial structure tile lies outside frozen source')
    merged = np.zeros((h, w), np.float32); occupied = np.zeros((h, w), bool)
    for record in selected:
        ref = check_ref(record.face_ref)
        if (recovery or {}).get((ref['face_instance_id'], 'facial_sculpt')) is not None:
            raise ValueError('Facial structure cannot consume generic recovery masks')
        window = record.window
        if (type(window) not in (tuple, list) or len(window) != 4
                or any(type(v) is not int for v in window)):
            raise ValueError('Facial structure field window is malformed')
        ry, rx, rh, rw = window; field = record.log_gain
        if (min(ry, rx) < 0 or min(rh, rw) < 1 or ry+rh > source_shape[0] or rx+rw > source_shape[1]
                or type(field) is not np.ndarray or field.dtype != np.float32 or field.shape != (rh, rw)
                or field.flags.writeable or not field.flags.c_contiguous or not np.isfinite(field).all()
                or np.any(np.abs(field) > BOUND) or record.delta is not None
                or record.chroma_shift is not None or record.weights is not None):
            raise ValueError('Facial structure requires its immutable source-owned scalar field')
        y0, x0 = max(ry, oy), max(rx, ox); y1, x1 = min(ry+rh, oy+h), min(rx+rw, ox+w)
        if y1 <= y0 or x1 <= x0:
            continue
        part = field[y0-ry:y1-ry, x0-rx:x1-rx]
        active = part != 0; used = occupied[y0-oy:y1-oy, x0-ox:x1-ox]
        take = active & ~used
        merged[y0-oy:y1-oy, x0-ox:x1-ox][take] = part[take]; used[take] = True
    field_t = torch.tensor(merged, dtype=torch.float32, device=pixels.device)[None, None]
    return apply_t(pixels, field_t)
