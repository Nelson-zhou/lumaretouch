# SPDX-License-Identifier: GPL-3.0-or-later
"""Feasible prepared source vector on actual upstream SDR pixels.

One scalar per pixel retains the prepared encoded-RGB vector direction without
channel clipping. This is not physical separation or perceptual hue invariance
following other colour edits. CPU/device parity and quality are AUTHORED / UNRUN.
"""


def apply_np(pixels, delta, *, label):
    import numpy as np
    if (type(pixels) is not np.ndarray or type(delta) is not np.ndarray
            or pixels.ndim != 3 or pixels.shape[-1] != 3 or pixels.shape != delta.shape
            or pixels.dtype != np.float32 or delta.dtype != np.float32):
        raise ValueError(f'{label} composition requires aligned float32 HWC RGB and delta')
    if not np.isfinite(delta).all():
        raise ValueError(f'{label} source delta is nonfinite')
    active = np.any(delta != 0, axis=-1, keepdims=True)
    if not np.any(active):
        return pixels
    invalid = ~np.isfinite(pixels) | (pixels < 0) | (pixels > 1)
    if np.any(invalid & active):
        raise ValueError(f'Active {label.lower()} composition cannot clip HDR or invalid upstream pixels')
    gain = np.ones_like(pixels[..., :1])
    for channel in range(3):
        component = delta[..., channel:channel+1]
        current = pixels[..., channel:channel+1]
        denominator = np.where(component != 0, component, np.float32(1))
        room = np.where(component > 0, 1-current, -current)
        permitted = np.where(component != 0, room/denominator, np.float32(1))
        gain = np.minimum(gain, permitted)
    gain = np.clip(gain, 0, 1)
    gain = np.where(gain < 1, gain*np.float32(1-4*np.finfo(np.float32).eps), gain)
    result = np.where(delta != 0, pixels+gain*delta, pixels)
    if np.any((~np.isfinite(result) | (result < 0) | (result > 1)) & active):
        raise ValueError(f'{label} vector feasibility failed; no channel-clipping fallback')
    return result


def apply_t(pixels, delta, *, label):
    import torch
    if (not isinstance(pixels, torch.Tensor) or not isinstance(delta, torch.Tensor)
            or pixels.ndim != 4 or pixels.shape[1] != 3 or pixels.shape != delta.shape
            or pixels.dtype != torch.float32 or delta.dtype != torch.float32
            or pixels.device != delta.device):
        raise ValueError(f'{label} composition requires aligned float32 NCHW RGB and delta')
    if not bool(torch.isfinite(delta).all()):
        raise ValueError(f'{label} source delta is nonfinite')
    active = delta.ne(0).any(dim=1, keepdim=True)
    if not bool(active.any()):
        return pixels
    invalid = ~torch.isfinite(pixels) | pixels.lt(0) | pixels.gt(1)
    if bool((invalid & active).any()):
        raise ValueError(f'Active {label.lower()} composition cannot clip HDR or invalid upstream pixels')
    gain = torch.ones_like(pixels[:, :1])
    for channel in range(3):
        component = delta[:, channel:channel+1]
        current = pixels[:, channel:channel+1]
        denominator = torch.where(component.ne(0), component, torch.ones_like(component))
        room = torch.where(component.gt(0), 1-current, -current)
        permitted = torch.where(component.ne(0), room/denominator, torch.ones_like(component))
        gain = torch.minimum(gain, permitted)
    gain = gain.clamp(0, 1)
    gain = torch.where(gain.lt(1), gain*(1-4*torch.finfo(torch.float32).eps), gain)
    result = torch.where(delta.ne(0), pixels+gain*delta, pixels)
    if bool(((~torch.isfinite(result) | result.lt(0) | result.gt(1)) & active).any()):
        raise ValueError(f'{label} vector feasibility failed; no channel-clipping fallback')
    return result
