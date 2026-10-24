# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply frozen clavicle light intent to the ACTUAL current source stage.

The sole pointwise effect algebra is Rust, including device-preview tiles.
Python only validates ownership/extent and transports bounded current-pixel
strips. No source RGB delta, repeated estimation, anatomy synthesis, RGB8
roundtrip, channel clipping or Python effect fallback. AUTHORED / UNRUN.
"""
import numpy as np

STAGE = 'collarbone'
MAX_CHUNK_PIXELS = 131072


def _selected(records):
    return sorted((r for r in records if r.stage == STAGE),
                  key=lambda r: r.face_ref['face_instance_id'])


def _extent(shape, source_shape, origin):
    from . import collarbone_native as N
    if (type(source_shape) not in (tuple, list) or len(source_shape) != 2
            or any(type(n) is not int or not 1 <= n <= N.MAX_DIMENSION for n in source_shape)
            or type(origin) not in (tuple, list) or len(origin) != 2
            or any(type(n) is not int or n < 0 for n in origin)):
        raise ValueError('Collarbone needs its exact full-source extent and tile origin')
    if source_shape[0]*source_shape[1] > N.MAX_PIXELS:
        raise MemoryError('Collarbone source exceeds its admitted pixel budget')
    h, w = shape; y, x = origin
    if min(h, w) < 1 or y+h > source_shape[0] or x+w > source_shape[1]:
        raise ValueError('Collarbone current pixels are outside the frozen source')


def _strips(y0, x0, y1, x1):
    rows = max(1, MAX_CHUNK_PIXELS // (x1-x0))
    for y in range(y0, y1, rows):
        yield y, x0, min(y+rows, y1), x1


def _records(selected, recovery, source_shape):
    from . import collarbone_state as S, collarbone_native as N
    from .people_state import check_ref
    result = []
    for record in selected:
        ref = check_ref(record.face_ref)
        if (recovery or {}).get((ref['face_instance_id'], STAGE)) is not None:
            raise ValueError('Collarbone support is not a generic face-recovery mask')
        window = record.window
        if (type(window) not in (tuple, list) or len(window) != 4
                or any(type(n) is not int for n in window)):
            raise ValueError('Collarbone field needs its exact source ROI')
        y, x, h, w = window
        if min(y, x) < 0 or min(h, w) < 1 or y+h > source_shape[0] or x+w > source_shape[1]:
            raise ValueError('Collarbone field exceeds its frozen source extent')
        field = record.log_gain
        if (type(field) is not np.ndarray or field.dtype != np.float32
                or field.shape != (h, w, 1) or field.flags.writeable
                or not field.flags.c_contiguous):
            raise ValueError('Collarbone needs an immutable source-owned float32 scalar field')
        if record.delta is not None or record.chroma_shift is not None or record.weights is not None:
            raise ValueError('Collarbone log-light intent cannot masquerade as an RGB/chroma delta')
        if type(record.amounts) is not dict or set(record.amounts) != {'amount'}:
            raise ValueError('Collarbone field lost its independently checked amount')
        amount = S.check({'version': S.VERSION, 'amount': record.amounts['amount']})['amount']
        for y0, x0, y1, x1 in _strips(0, 0, h, w):
            part = field[y0:y1, x0:x1, 0]
            if not np.isfinite(part).all() or np.any(np.abs(part) > N.MAX_LOG_GAIN+N.FIELD_TOLERANCE):
                raise ValueError('Collarbone field is nonfinite or exceeds its signed log-light bound')
        result.append((record, amount))
    return result


def _chunks(record, amount, origin, shape, occupied):
    """Source-coordinate intersections only; never rescale or re-solve a field."""
    if amount == 0:
        return
    oy, ox = origin; h, w = shape
    ry, rx, rh, rw = record.window
    y0, x0 = max(ry, oy), max(rx, ox)
    y1, x1 = min(ry+rh, oy+h), min(rx+rw, ox+w)
    if y1 <= y0 or x1 <= x0:
        return
    for y, x, end_y, end_x in _strips(y0, x0, y1, x1):
        field = record.log_gain[y-ry:end_y-ry, x-rx:end_x-rx, 0]
        active = field != 0
        if not np.any(active):
            continue
        used = occupied[y-oy:end_y-oy, x-ox:end_x-ox]
        if np.any(active & used):
            raise ValueError('Collarbone fields overlap another retained owner; no silent priority winner')
        used[active] = True
        yield y, x, end_y, end_x, field


def _apply(current, field, amount, *, x, y, source_shape):
    from .collarbone_native import compose_field
    corrected = compose_field(current, field, amount, field_origin=(x, y),
                              source_shape=tuple(source_shape), origin=(x, y))
    if (type(corrected) is not np.ndarray or corrected.dtype != np.float32
            or corrected.shape != current.shape or not np.isfinite(corrected).all()
            or np.any((corrected < 0) | (corrected > 1))):
        raise ValueError('Collarbone native composition returned invalid current-stage pixels')
    inactive = field == 0
    if not np.array_equal(corrected[inactive], current[inactive]):
        raise ValueError('Collarbone native composition changed unowned current-stage pixels')
    return corrected


def apply_records_np(current, records, recovery=None):
    selected = _selected(records)
    if not selected:
        return current, {'stage': STAGE, 'overlap_pixels': 0, 'changed_pixels': 0}
    if (type(current) is not np.ndarray or current.dtype != np.float32
            or current.ndim != 3 or current.shape[2] != 3):
        raise ValueError('Collarbone requires current float32 RGB; alpha is unsupported')
    h, w = current.shape[:2]
    _extent((h, w), (h, w), (0, 0))
    checked = _records(selected, recovery, (h, w))
    for y, x, end_y, end_x in _strips(0, 0, h, w):
        pixels = current[y:end_y, x:end_x]
        if not np.isfinite(pixels).all() or np.any((pixels < 0) | (pixels > 1)):
            raise ValueError('Collarbone refuses HDR or nonfinite current-stage RGB, never clips')
    occupied = np.zeros((h, w), bool); output = current; changed = 0
    for record, amount in checked:
        for y, x, end_y, end_x, field in _chunks(record, amount, (0, 0), (h, w), occupied):
            pixels = current[y:end_y, x:end_x]
            corrected = _apply(pixels, field, amount, x=x, y=y, source_shape=(h, w))
            count = int(np.count_nonzero(np.any(corrected != pixels, axis=2)))
            if not count:
                continue
            if output is current:
                output = current.copy()
            output[y:end_y, x:end_x] = corrected; changed += count
    return output, {'stage': STAGE, 'overlap_pixels': 0, 'changed_pixels': changed,
                    'application': 'rust-current-stage-linear-RGB', 'runtime_quality_accepted': False}


def apply_records_t(pixels, records, recovery=None, *, source_shape, origin=(0, 0)):
    """Same native application for preview/full candidate/export tile pixels.

    Origin is the existing pipeline's (y,x), converted explicitly at the Rust
    boundary. Only intersecting float32 strips cross the device boundary. This
    bounded transport is source-level design, not measured latency/VRAM proof.
    """
    selected = _selected(records)
    if not selected:
        return pixels
    import torch
    if (not isinstance(pixels, torch.Tensor) or pixels.dtype != torch.float32
            or pixels.ndim != 4 or pixels.shape[0] != 1 or pixels.shape[1] != 3):
        raise ValueError('Collarbone requires current float32 NCHW RGB; alpha is unsupported')
    h, w = pixels.shape[2:]
    _extent((h, w), source_shape, origin)
    oy, ox = origin
    checked = _records(selected, recovery, source_shape)
    for y, x, end_y, end_x in _strips(0, 0, h, w):
        part = pixels[:, :, y:end_y, x:end_x]
        if not bool(torch.isfinite(part).all()) or bool(torch.any((part < 0) | (part > 1))):
            raise ValueError('Collarbone refuses HDR or nonfinite current-stage RGB, never clips')
    occupied = np.zeros((h, w), bool); output = pixels
    for record, amount in checked:
        for y, x, end_y, end_x, field in _chunks(record, amount, origin, (h, w), occupied):
            current = pixels[0, :, y-oy:end_y-oy, x-ox:end_x-ox]
            current = current.detach().permute(1, 2, 0).contiguous().to('cpu').numpy()
            corrected = _apply(current, field, amount, x=x, y=y, source_shape=source_shape)
            if np.array_equal(corrected, current):
                continue
            if output is pixels:
                output = pixels.clone()
            result = torch.tensor(corrected, device=pixels.device, dtype=pixels.dtype).permute(2, 0, 1)
            output[0, :, y-oy:end_y-oy, x-ox:end_x-ox] = result
    return output
