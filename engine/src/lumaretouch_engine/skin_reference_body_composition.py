# SPDX-License-Identifier: GPL-3.0-or-later
"""Selected-face BODY colour/brightness on CURRENT pixels, before ONE warp.

AUTHORED / UNRUN. No source-delta replay, own-face-only chroma substitution,
per-tile fit, image8 quantization, second geometry warp or partial publication.
The complete matching face/body bank is preflighted before native body apply.
"""
import numpy as np

from . import skin_reference_match_native as N, skin_reference_match_runtime as F
from .cpu_memory_budget import available_estimate
from .skin_reference_body_runtime import (STAGE, BLOCK_PIXELS, RECORD_BYTES,
    array_bytes, validate_joint_records, _poll, _shape)

FIXED_BYTES = 32 * 1024**2


def _valid(value, cancelled):
    for row in value:
        for left in range(0, row.shape[0], BLOCK_PIXELS):
            _poll(cancelled); block = row[left:left+BLOCK_PIXELS]
            if not np.isfinite(block).all() or np.any(block < 0) or np.any(block > 1):
                raise ValueError('Body-reference composition requires finite SDR current pixels')


def _admit(required, byte_budget):
    if byte_budget is not None and (type(byte_budget) is not int or byte_budget < 0):
        raise ValueError('Body-reference composition budget must be a nonnegative total allowance')
    allowed = available_estimate() if byte_budget is None else min(byte_budget, available_estimate())
    if required > allowed:
        raise MemoryError('Body-reference private all-target composition exceeds memory admission')
    return allowed


def apply_records_np(current, records, recovery=None, *, source_shape=None,
                     origin=(0, 0), byte_budget=None, cancelled=lambda: False):
    """Apply body records; include FACE records for complete overlap preflight.

    source_shape names the unchanged application grid; origin is its exact (y,x)
    crop offset. Fit ROI dimensions are independent from this current tile.
    """
    records = tuple(records)
    selected = tuple(record for record in records if record.stage == STAGE)
    if not selected:
        return current, {'stage': STAGE, 'changed_pixels': 0, 'overlap_pixels': 0}
    _poll(cancelled)
    if (type(current) is not np.ndarray or current.dtype != np.float32
            or current.ndim != 3 or current.shape[2] != 3 or min(current.shape[:2]) < 1):
        raise ValueError('Body-reference composition needs current HWC3 native float32 RGB')
    h, w = current.shape[:2]
    source_shape = _shape(tuple(current.shape[:2]) if source_shape is None else source_shape)
    if (type(origin) is not tuple or len(origin) != 2
            or any(type(v) is not int or v < 0 for v in origin)):
        raise ValueError('Body-reference tile origin must be an exact nonnegative (y,x) tuple')
    oy, ox = origin
    if oy+h > source_shape[0] or ox+w > source_shape[1]:
        raise ValueError('Body-reference tile lies outside the declared application grid')
    if recovery is not None and type(recovery) is not dict:
        raise ValueError('Body-reference recovery must be the canonical map or absent')
    joint = tuple(record for record in records if record.stage in (STAGE, F.STAGE))
    retained = sum(array_bytes(record.weights)+RECORD_BYTES for record in joint)
    tile_pixels = min(h*w, N.MAX_APPLY_PIXELS)
    native_bytes = 40*tile_pixels + N.APPLY_FIXED_SCRATCH_BYTES + N.SCRATCH_BYTES
    resident = array_bytes(current) + retained + h*w*12 + FIXED_BYTES
    allowed = _admit(resident+native_bytes+tile_pixels*16, byte_budget)
    _valid(current, cancelled)
    # This validates the FULL grid even for a crop. Overlap outside the current
    # tile or a corrupt later target cannot be hidden by tile-local ordering.
    validate_joint_records(joint, application_shape=source_shape, cancelled=cancelled)
    planned = []
    for record in selected:
        _poll(cancelled); params = record.amounts
        if (recovery or {}).get((record.face_ref['face_instance_id'], STAGE)) is not None:
            raise ValueError('Body-reference matching cannot borrow another operation recovery mask')
        y, x, rh, rw = record.window
        y0, x0, y1, x1 = max(y, oy), max(x, ox), min(y+rh, oy+h), min(x+rw, ox+w)
        if params.amount != 0 and y1 > y0 and x1 > x0:
            planned.append((record, y0, x0, y1, x1))
    result = current; changed = 0
    for record, y0, x0, y1, x1 in planned:
        y, x, _, _ = record.window; params = record.amounts
        rows = max(1, N.MAX_APPLY_PIXELS//(x1-x0))
        for top in range(y0, y1, rows):
            _poll(cancelled); bottom = min(top+rows, y1)
            coverage = record.weights[top-y:bottom-y, x0-x:x1-x]
            if not np.any(coverage > 0):
                continue
            before = current[top-oy:bottom-oy, x0-ox:x1-ox]
            updated = N.apply(before, coverage, params.measured_fit, params.amount,
                              byte_budget=allowed-resident, cancelled=cancelled)
            if type(updated) is not np.ndarray or updated.dtype != np.float32 or updated.shape != before.shape:
                raise RuntimeError('Body-reference native result has an invalid tile layout')
            _valid(updated, cancelled)
            for row in range(updated.shape[0]):
                for left in range(0, updated.shape[1], BLOCK_PIXELS):
                    _poll(cancelled); right = min(left+BLOCK_PIXELS, updated.shape[1])
                    take = coverage[row, left:right] > 0
                    old, new = before[row, left:right], updated[row, left:right]
                    different = np.any(old.view(np.uint32) != new.view(np.uint32), axis=-1)
                    protected = ~take | np.all(old == 0, axis=-1) | np.all(old == 1, axis=-1)
                    if all(value == 0 for value in params.measured_fit.transform[1:]):
                        protected = np.ones_like(take)
                    if np.any(different & protected):
                        raise RuntimeError('Body-reference native output changed protected or exact neutral pixels')
                    count = int(np.count_nonzero(different & take))
                    if count:
                        if result is current:
                            result = current.copy()
                        destination = result[top-oy+row, x0-ox+left:x0-ox+right]
                        destination[take] = new[take]; changed += count
            del updated
    _poll(cancelled)
    return result, {'stage': STAGE, 'changed_pixels': changed, 'overlap_pixels': 0,
                    'composition': 'original-rust-current-pixel-colour-and-brightness',
                    'reference_face_unchanged_by_this_operation': True}


def apply_records_t(pixels, records, recovery=None, *, source_shape,
                    origin=(0, 0), byte_budget=None, cancelled=lambda: False):
    records = tuple(records)
    if not any(record.stage == STAGE for record in records):
        return pixels
    import torch
    if (not isinstance(pixels, torch.Tensor) or pixels.dtype != torch.float32 or pixels.ndim != 4
            or pixels.shape[0] != 1 or pixels.shape[1] != 3):
        raise ValueError('Body-reference tensor requires current float32 NCHW RGB')
    _poll(cancelled)
    transfer_bytes = int(pixels.numel())*4*3 + FIXED_BYTES
    allowed = _admit(transfer_bytes, byte_budget)
    current = np.array(pixels[0].permute(1, 2, 0).detach().to('cpu').numpy(),
                       dtype=np.float32, order='C', copy=True)
    result, _ = apply_records_np(current, records, recovery, source_shape=source_shape,
        origin=origin, byte_budget=allowed-transfer_bytes, cancelled=cancelled)
    if result is current:
        return pixels
    _poll(cancelled)
    output = torch.from_numpy(result).permute(2, 0, 1)[None].to(device=pixels.device, dtype=pixels.dtype)
    _poll(cancelled)
    return output
