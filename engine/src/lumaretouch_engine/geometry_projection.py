"""The existing production crop/rotation/resize projection, shared by action inputs.

No inverse-coordinate approximation and no changed interpolation defaults.
"""
from .ops.geometry import crop_rotate_t, is_identity


def project(tensor, rect, rotation, target):
    if is_identity(rect, rotation):
        return tensor
    import torch
    import torch.nn.functional as F
    if tensor.dim() == 4:
        if tensor.shape[0] != 1:
            raise ValueError('Geometry projection requires one image')
        hwc = tensor.permute(0,2,3,1)[0]
    elif tensor.dim() == 3:
        hwc = tensor
    else:
        raise ValueError('Geometry projection requires HWC or single NCHW')
    out = crop_rotate_t(hwc, rect, rotation, uint8=False)
    width, height = target
    if (out.shape[0], out.shape[1]) != (height, width):
        out = F.interpolate(out.permute(2,0,1)[None], size=(height,width),
                            mode='bilinear', align_corners=False)[0].permute(1,2,0)
    if tensor.dim() == 4:
        out = out.permute(2,0,1).contiguous()[None]
    if not torch.isfinite(out).all():
        raise ValueError(f'裁剪/旋转产出非有限值，已拒：{rect} {rotation}')
    return out
