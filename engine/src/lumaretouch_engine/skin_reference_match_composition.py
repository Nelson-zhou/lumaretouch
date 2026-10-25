# SPDX-License-Identifier: GPL-3.0-or-later
"""Original Rust CURRENT-pixel composition, before the ONE warp. UNRUN.

Prepared fits never see repairs, portrait edits or export tiles as fit sources.
Every record is preflighted before native calls; all updated pixels stay private
until every target/tile and the final cancellation check have succeeded.
"""
import numpy as np

from . import people_state as P, skin_reference_match_native as N
from .cpu_memory_budget import available_estimate
from .skin_reference_match_runtime import (STAGE, Parameters, BLOCK_PIXELS, RECORD_BYTES,
    array_bytes, coverage_digest, _identity, _poll, _shape, _window)

FIXED_BYTES = 32 * 1024**2


def _blocks(value):
    for row in range(value.shape[0]):
        for left in range(0, value.shape[1], BLOCK_PIXELS):
            yield value[row, left:left + BLOCK_PIXELS]


def _valid(value, cancelled):
    for block in _blocks(value):
        _poll(cancelled)
        if not np.isfinite(block).all() or np.any(block < 0) or np.any(block > 1):
            raise ValueError('Skin-reference composition requires finite SDR current pixels and coverage')


def _admit(required, byte_budget):
    if byte_budget is not None and (type(byte_budget) is not int or byte_budget < 0):
        raise ValueError('Skin-reference composition byte budget must be a nonnegative total allowance')
    allowed = available_estimate() if byte_budget is None else min(byte_budget, available_estimate())
    if required > allowed:
        raise MemoryError('Skin-reference private all-target composition exceeds memory admission')
    return allowed


def apply_records_np(current, records, recovery=None, *, source_shape=None,
                     origin=(0, 0), byte_budget=None, cancelled=lambda: False):
    """Apply this stage using application-grid (y,x) origin, including crop tiles."""
    selected = tuple(record for record in records if record.stage == STAGE)
    if not selected:
        return current, {'stage': STAGE, 'changed_pixels': 0, 'overlap_pixels': 0}
    _poll(cancelled)
    if (type(current) is not np.ndarray or current.dtype != np.float32
            or current.ndim != 3 or current.shape[2] != 3 or min(current.shape[:2]) < 1):
        raise ValueError('Skin-reference composition needs actual current HWC3 native float32 RGB')
    h, w = current.shape[:2]
    source_shape = _shape(tuple(current.shape[:2]) if source_shape is None else source_shape)
    if (type(origin) is not tuple or len(origin) != 2
            or any(type(v) is not int or v < 0 for v in origin)):
        raise ValueError('Skin-reference tile origin must be an exact nonnegative (y,x) tuple')
    oy, ox = origin
    if oy+h > source_shape[0] or ox+w > source_shape[1]:
        raise ValueError('Skin-reference current tile is outside its declared application grid')
    if recovery is not None and type(recovery) is not dict:
        raise ValueError('Skin-reference recovery must be the canonical map or absent')
    retained = sum(array_bytes(record.weights) for record in selected) + RECORD_BYTES*len(selected)
    # Narrow target windows can admit more rows than the full frame. Charge
    # the absolute tile-pixel upper bound, not the first window's row count.
    tile_pixels = min(h*w, N.MAX_APPLY_PIXELS)
    native_bytes = 40*tile_pixels + N.APPLY_FIXED_SCRATCH_BYTES + N.SCRATCH_BYTES
    # Caller input/backing + retained weights + private output + occupied plane,
    # full native snapshots/output/staging + masked copy/validation scratch.
    resident = array_bytes(current) + retained + h*w*13 + FIXED_BYTES
    allowed = _admit(resident + native_bytes + tile_pixels*16, byte_budget)
    _valid(current, cancelled)
    occupied = np.zeros((h, w), dtype=bool)
    planned, seen, common = [], set(), None
    for record in selected:
        _poll(cancelled)
        params = record.amounts
        if type(params) is not Parameters:
            raise ValueError('Skin-reference stage lacks its measured source-owned parameters')
        params.checked(); ref = P.check_ref(record.face_ref)
        if (_identity(ref) != params.target_identity or params.application_shape != source_shape
                or record.window != params.application_window):
            raise ValueError('Skin-reference record belongs to another face, window or application grid')
        identity = (params.source_sha256, params.source_pixels_sha256,
                    params.source_shape, params.application_shape, params.reference_identity)
        if common is not None and common != identity:
            raise ValueError('Skin-reference target bank disagrees on its source or selected reference')
        common = identity
        if ref['face_instance_id'] in seen:
            raise ValueError('Skin-reference target bank contains a duplicate face')
        seen.add(ref['face_instance_id'])
        if (recovery or {}).get((ref['face_instance_id'], STAGE)) is not None:
            raise ValueError('Skin-reference matching cannot borrow another operation recovery mask')
        if any(value is not None for value in (record.delta, record.chroma_shift, record.log_gain)):
            raise ValueError('Skin-reference matching cannot replay source RGB deltas or another algorithm')
        y, x, rh, rw = _window(record.window, source_shape); weights = record.weights
        if (type(weights) is not np.ndarray or weights.dtype != np.float32
                or weights.shape != (rh, rw) or weights.flags.writeable or not weights.flags.c_contiguous):
            raise ValueError('Skin-reference coverage must be its immutable contiguous reviewed plane')
        _valid(weights, cancelled)
        if coverage_digest(weights) != params.coverage_sha256:
            raise ValueError('Skin-reference coverage changed after full-source preparation')
        y0, x0 = max(y, oy), max(x, ox)
        y1, x1 = min(y+rh, oy+h), min(x+rw, ox+w)
        if params.amount == 0 or y1 <= y0 or x1 <= x0:
            continue
        # Preflight the complete local bank before the first native call. Full
        # application-grid ownership was already checked during preparation.
        for top in range(y0, y1):
            for left in range(x0, x1, BLOCK_PIXELS):
                _poll(cancelled); right = min(left+BLOCK_PIXELS, x1)
                visible = weights[top-y, left-x:right-x] > 0
                used = occupied[top-oy, left-ox:right-ox]
                if np.any(visible & used):
                    raise ValueError('Skin-reference target ownership overlaps; no partial stage published')
                used |= visible
        planned.append((record, y0, x0, y1, x1))
    if common is not None and common[-1][1] in seen:
        raise ValueError('Skin-reference selected reference must remain unchanged by this operation')
    result = current; changed = 0
    for record, y0, x0, y1, x1 in planned:
        y, x, _, _ = record.window; params = record.amounts
        rows = max(1, N.MAX_APPLY_PIXELS // (x1-x0))
        for top in range(y0, y1, rows):
            _poll(cancelled); bottom = min(top+rows, y1)
            coverage = record.weights[top-y:bottom-y, x0-x:x1-x]
            if not np.any(coverage > 0):
                continue
            # Strided views are allowed: the native boundary makes bounded,
            # private immutable snapshots. It consumes CURRENT, not fit RGB.
            before = current[top-oy:bottom-oy, x0-ox:x1-ox]
            updated = N.apply(before, coverage, params.measured_fit, params.amount,
                              byte_budget=allowed-resident, cancelled=cancelled)
            if type(updated) is not np.ndarray or updated.dtype != np.float32 or updated.shape != before.shape:
                raise RuntimeError('Skin-reference native result has an invalid tile layout')
            _valid(updated, cancelled)
            for row in range(updated.shape[0]):
                for left in range(0, updated.shape[1], BLOCK_PIXELS):
                    _poll(cancelled); right = min(left+BLOCK_PIXELS, updated.shape[1])
                    take = coverage[row, left:right] > 0
                    old = before[row, left:right]; new = updated[row, left:right]
                    different = np.any(old.view(np.uint32) != new.view(np.uint32), axis=-1)
                    protected = ~take | np.all(old == 0, axis=-1) | np.all(old == 1, axis=-1)
                    if all(value == 0 for value in params.measured_fit.transform[1:]):
                        protected = np.ones_like(take)
                    if np.any(different & protected):
                        raise RuntimeError('Skin-reference native output changed protected or exact neutral pixels')
                    count = int(np.count_nonzero(different & take))
                    if count:
                        if result is current:
                            result = current.copy()
                        destination = result[top-oy+row, x0-ox+left:x0-ox+right]
                        destination[take] = new[take]; changed += count
            del updated
    _poll(cancelled)
    return result, {'stage': STAGE, 'changed_pixels': changed, 'overlap_pixels': 0,
                    'composition': 'original-rust-current-pixel-colour-and-brightness'}


def apply_records_t(pixels, records, recovery=None, *, source_shape,
                    origin=(0, 0), byte_budget=None, cancelled=lambda: False):
    selected = tuple(record for record in records if record.stage == STAGE)
    if not selected:
        return pixels
    import torch
    if (not isinstance(pixels, torch.Tensor) or pixels.dtype != torch.float32 or pixels.ndim != 4
            or pixels.shape[0] != 1 or pixels.shape[1] != 3):
        raise ValueError('Skin-reference tensor requires current float32 NCHW RGB')
    _poll(cancelled)
    # CPU transfer + contiguous copy + copyback are charged while the complete
    # all-target NumPy transaction remains private. No alternate GPU algorithm.
    transfer_bytes = int(pixels.numel())*4*3 + FIXED_BYTES
    allowed = _admit(transfer_bytes, byte_budget)
    current = np.array(pixels[0].permute(1, 2, 0).detach().to('cpu').numpy(),
                       dtype=np.float32, order='C', copy=True)
    result, _ = apply_records_np(current, selected, recovery, source_shape=source_shape,
        origin=origin, byte_budget=allowed-transfer_bytes, cancelled=cancelled)
    if result is current:
        return pixels
    _poll(cancelled)
    output = torch.from_numpy(result).permute(2, 0, 1)[None].to(device=pixels.device, dtype=pixels.dtype)
    _poll(cancelled)
    return output
