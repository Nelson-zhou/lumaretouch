# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply frozen source log-chroma intent to actual current-stage luminance.

No neighbourhood/reference is re-solved on an export tile. No RGB delta from an
older stage is added here. Unsupported HDR/alpha inputs are refused, not clipped.
"""
import numpy as np


def apply_records_np(current, records, recovery=None):
    from . import skin_evenness_native as native
    selected = sorted((r for r in records if r.stage == 'skin_evenness'),
                      key=lambda r: r.face_ref['face_instance_id'])
    if not selected:
        return current, {'stage': 'skin_evenness', 'overlap_pixels': 0, 'changed_pixels': 0}
    if type(current) is not np.ndarray or current.dtype != np.float32 or current.ndim != 3 or current.shape[2] != 3:
        raise ValueError('Skin evenness needs actual current float32 RGB')
    if not np.isfinite(current).all() or np.any((current < 0) | (current > 1)):
        raise ValueError('Skin evenness does not support HDR or nonfinite input')
    h, w = current.shape[:2]
    occupied = np.zeros((h, w), bool); output = current; overlap = 0
    for record in selected:
        if (recovery or {}).get((record.face_ref['face_instance_id'], 'skin_evenness')) is not None:
            raise ValueError('Skin evenness has no reviewed dedicated recovery consumer')
        y, x, rh, rw = record.window; shift = record.chroma_shift
        if min(y, x) < 0 or min(rh, rw) <= 0 or y+rh > h or x+rw > w:
            raise ValueError('Skin evenness field is outside its source frame')
        if type(shift) is not np.ndarray or shift.dtype != np.float32 or shift.shape != (rh, rw, 2):
            raise ValueError('Skin evenness requires a source-owned two-channel field')
        if not np.isfinite(shift).all() or np.any(np.linalg.norm(shift.astype(np.float64), axis=2) > .0900001):
            raise ValueError('Skin evenness field exceeds its chroma bound')
        active = np.any(shift != 0, axis=2); used = occupied[y:y+rh, x:x+rw]
        overlap += int(np.count_nonzero(active & used)); take = active & ~used
        if not np.any(take): continue
        corrected = native.apply(current[y:y+rh, x:x+rw], shift)
        if output is current: output = current.copy()
        output[y:y+rh, x:x+rw][take] = corrected[take]; used[take] = True
    return output, {'stage': 'skin_evenness', 'overlap_pixels': overlap,
                    'changed_pixels': int(np.count_nonzero(np.any(output != current, axis=2)))}


def _apply_chunk_t(pixels, shift):
    """Pointwise native algebra in float64; final publication keeps tensor dtype."""
    import torch
    if pixels.ndim != 4 or pixels.shape[1] != 3 or shift.shape != (pixels.shape[0], 2, *pixels.shape[2:]):
        raise ValueError('Skin evenness tensor/field shape mismatch')
    if not torch.isfinite(pixels).all() or torch.any((pixels < 0) | (pixels > 1)):
        raise ValueError('Skin evenness requires bounded finite working-sRGB')
    if not torch.isfinite(shift).all() or torch.any(torch.linalg.vector_norm(shift.to(torch.float64), dim=1) > .0900001):
        raise ValueError('Skin evenness field exceeds its chroma bound')
    if not torch.any(shift != 0): return pixels
    encoded = pixels.to(torch.float64); field = shift.to(torch.float64)
    linear = torch.where(encoded <= .04045, encoded/12.92, ((encoded+.055)/1.055).pow(2.4))
    gains = torch.cat((field[:, 0:1].exp(), torch.ones_like(field[:, 0:1]), field[:, 1:2].exp()), dim=1)
    coefficients = torch.tensor([.2126, .7152, .0722], device=pixels.device, dtype=torch.float64)[None, :, None, None]
    proposal = linear*gains; luminance = (linear*coefficients).sum(dim=1, keepdim=True)
    proposal_y = (proposal*coefficients).sum(dim=1, keepdim=True)
    proposal = proposal*(luminance/torch.where(proposal_y > 0, proposal_y, torch.ones_like(proposal_y)))
    delta = proposal-linear
    safe = torch.where(delta != 0, delta, torch.ones_like(delta))
    bound = torch.where(delta > 0, (1-linear)/safe,
                        torch.where(delta < 0, -linear/safe, torch.ones_like(delta)))
    amount = torch.minimum(bound.amin(dim=1, keepdim=True), torch.ones_like(luminance))
    amount = torch.where(amount < 1, amount*(1-1e-12), amount)
    target = linear+amount*delta
    # pow sees only nonnegative values; this guard refuses a numerical failure,
    # rather than silently replacing the advertised common-vector gamut policy.
    if torch.any((target < 0) | (target > 1)) or not torch.isfinite(target).all():
        raise ValueError('Skin evenness common-vector gamut failure')
    result = torch.where(target <= .0031308, 12.92*target, 1.055*target.pow(1/2.4)-.055)
    unchanged = (~field.ne(0).any(dim=1, keepdim=True) | encoded.eq(0).all(dim=1, keepdim=True)
                 | encoded.eq(1).all(dim=1, keepdim=True) | amount.eq(0) | delta.eq(0).all(dim=1, keepdim=True))
    return torch.where(unchanged, pixels, result.to(pixels.dtype))


def apply_t(pixels, shift):
    """Bound float64 temporaries to at most 131072 pixels per row strip.

    Full output and the frozen two-channel field still count as resident data.
    This is a source-level allocation policy, not measured peak/latency evidence.
    """
    import torch
    if (not isinstance(pixels, torch.Tensor) or not isinstance(shift, torch.Tensor)
            or pixels.dtype != torch.float32 or shift.dtype != torch.float32
            or pixels.device != shift.device or pixels.ndim != 4 or pixels.shape[0] != 1
            or pixels.shape[1] != 3 or min(pixels.shape[2:]) < 1
            or shift.shape != (1, 2, *pixels.shape[2:])):
        raise ValueError('Skin evenness needs aligned float32 NCHW current pixels and field')
    if not torch.any(shift != 0): return pixels
    width = pixels.shape[3]
    if width > 65536:
        raise ValueError('Skin evenness dimension exceeds the native contract')
    rows = max(1, 131072//width)
    output = torch.empty_like(pixels)
    for y in range(0, pixels.shape[2], rows):
        output[:, :, y:y+rows] = _apply_chunk_t(pixels[:, :, y:y+rows], shift[:, :, y:y+rows])
    return output
