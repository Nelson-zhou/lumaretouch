"""One Rust colour solver shared by CPU reference and Torch preview/export hosts.

Only measured teeth support is processed. Transfers are bounded to its bounding
rectangle; this is a CPU kernel and makes no GPU latency claim. No segmentation,
model download, generated teeth, reconstruction, or second numerical fallback.
"""
import numpy as np

KEYS = ('teeth_brightness', 'teeth_yellow_removal')


def active(amounts):
    return any(amounts.get(key, 0) > 0 for key in KEYS)


def _bounds(weight):
    locations = np.argwhere(weight > 0)
    if not len(locations):
        return None
    y0, x0 = locations.min(axis=0)
    y1, x1 = locations.max(axis=0) + 1
    return int(y0), int(x0), int(y1), int(x1)


def numpy_apply(pixels, weight, amounts, *, cancelled=lambda: False):
    if not active(amounts):
        return pixels
    if cancelled():
        raise InterruptedError("Teeth colour cancelled before buffer transfer")
    from .teeth_colour_native import apply
    source = np.asarray(pixels)
    mask = np.asarray(weight)
    if source.ndim < 3 or source.shape[-1] != 3 or mask.shape != source.shape[-3:-1]:
        raise ValueError('Teeth colour source and measured support dimensions differ')
    if not np.isfinite(mask).all() or np.any((mask < 0) | (mask > 1)):
        raise ValueError('Teeth colour support must be finite coverage')
    bounds = _bounds(mask)
    if bounds is None:
        return pixels
    y0,x0,y1,x1 = bounds
    output = source.copy()
    frames = output.reshape((-1, *source.shape[-3:]))
    support = np.ascontiguousarray(mask[y0:y1,x0:x1], dtype=np.float32)
    for frame in frames:
        original = frame[y0:y1,x0:x1]
        if not np.isfinite(original).all() or np.any((original < 0) | (original > 1)):
            raise ValueError('Independent teeth colour requires SDR input; no implicit clipping')
        frozen = np.ascontiguousarray(original, dtype=np.float32)
        corrected = apply(frozen, support, amounts.get(KEYS[0],0), amounts.get(KEYS[1],0), cancelled=cancelled)
        delta = corrected - frozen
        # Preserve higher-precision originals wherever the Rust solver is neutral,
        # including non-yellow teeth when only yellow reduction is requested.
        frame[y0:y1,x0:x1] = np.where(delta != 0, original + delta.astype(original.dtype, copy=False), original)
    return output


def tensor_apply(pixels, weight, amounts, *, cancelled=lambda: False):
    if not active(amounts):
        return pixels
    if cancelled():
        raise InterruptedError("Teeth colour cancelled before buffer transfer")
    import torch
    if pixels.ndim != 4 or pixels.shape[1] != 3 or tuple(weight.shape) != tuple(pixels.shape[-2:]):
        raise ValueError('Teeth colour tensor/support layout mismatch')
    if not torch.isfinite(weight).all() or ((weight < 0) | (weight > 1)).any():
        raise ValueError('Teeth colour support must be finite coverage')
    locations = torch.nonzero(weight > 0, as_tuple=False)
    if not locations.numel():
        return pixels
    y0,x0 = (int(v) for v in locations.amin(dim=0))
    y1,x1 = (int(v)+1 for v in locations.amax(dim=0))
    crop = pixels[:,:,y0:y1,x0:x1]
    if not torch.isfinite(crop).all() or ((crop < 0) | (crop > 1)).any():
        raise ValueError('Independent teeth colour requires SDR input; no implicit clipping')
    cpu = crop.detach().to(device='cpu', dtype=torch.float32).permute(0,2,3,1).contiguous().numpy()
    mask = weight[y0:y1,x0:x1].detach().to(device='cpu', dtype=torch.float32).contiguous().numpy()
    corrected = numpy_apply(cpu, mask, amounts, cancelled=cancelled)
    delta = torch.as_tensor(corrected - cpu, device=pixels.device, dtype=pixels.dtype).permute(0,3,1,2)
    out = pixels.clone()
    out[:,:,y0:y1,x0:x1] = torch.where(delta != 0, crop + delta, crop)
    return out


def capability():
    from .teeth_colour_native import available
    ready = available()
    return {'teeth_colour_available': ready,
            'teeth_colour_reason': None if ready else '独立牙齿调整 Rust 核心未安装或 ABI 不匹配；不会使用替代滤镜'}
