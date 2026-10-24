# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply the prepared skin vector to the actual upstream SDR pixels safely.

The prepared source delta may meet a different input after smoothing, fabric or
light edits. Per-channel clipping there would invalidate the native cores'
direction/gamut contracts. Limit ONE scalar per pixel against current headroom
instead, without changing other portrait stages. This is encoded-working-RGB
vector feasibility, not perceptual hue preservation or a new image algorithm.
AUTHORED / UNRUN; device synchronization, memory and photo quality need validation.
"""


def apply(pixels, delta):
    import torch
    if (not isinstance(pixels, torch.Tensor) or not isinstance(delta, torch.Tensor)
            or pixels.ndim != 4 or pixels.shape[1] != 3 or pixels.shape != delta.shape
            or pixels.dtype != torch.float32 or delta.dtype != torch.float32
            or pixels.device != delta.device):
        raise ValueError('Skin composition requires aligned float32 NCHW RGB and source delta')
    if not bool(torch.isfinite(delta).all()):
        raise ValueError('Skin source delta is nonfinite; no partial result published')
    active = delta.ne(0).any(dim=1, keepdim=True)
    if not bool(active.any()):
        return pixels
    invalid = ~torch.isfinite(pixels) | pixels.lt(0) | pixels.gt(1)
    if bool((invalid & active).any()):
        raise ValueError('Active skin composition cannot clip HDR or invalid upstream pixels')
    # One-channel rolling minimum avoids allocating a second RGB ratio image.
    # Bounds clamp the gain only, never any output colour channel.
    gain = torch.ones_like(pixels[:, :1])
    for channel in range(3):
        component = delta[:, channel:channel+1]
        current = pixels[:, channel:channel+1]
        denominator = torch.where(component.ne(0), component, torch.ones_like(component))
        room = torch.where(component.gt(0), 1-current, -current)
        permitted = torch.where(component.ne(0), room/denominator, torch.ones_like(component))
        gain = torch.minimum(gain, permitted)
    gain = gain.clamp(0, 1)
    # A reduced gain stays inside the boundary despite ratio rounding. A fully
    # feasible vector remains unscaled, preserving existing ordinary results.
    gain = torch.where(gain.lt(1), gain*(1-4*torch.finfo(torch.float32).eps), gain)
    result = torch.where(delta.ne(0), pixels+gain*delta, pixels)
    invalid_result = ~torch.isfinite(result) | result.lt(0) | result.gt(1)
    if bool((invalid_result & active).any()):
        raise ValueError('Skin vector feasibility failed; no channel-clipping fallback')
    return result
