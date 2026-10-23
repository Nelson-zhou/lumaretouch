"""Source-resolved grain delivery. Preserve geometry/colour/detail stage order."""
from copy import copy
import numpy as np


def render_delivery(source,spec,*,renderer,device,tile,progress,bits,geometry):
    from .ops.upscale import Plan,unsharp_float_bands_np
    from .optics_export import upscale
    upstream=copy(spec)
    upstream.scale=1;upstream.sharpen_amount=0.;upstream.float_output=True
    full,stats=renderer(source,upstream,device=device,tile=tile,progress=progress,bits=bits,geometry=geometry)
    def cancelled():
        if progress:progress(0,1,0.)
        return False
    h,w=full.shape[:2]
    if geometry is not None:
        from .ops.geometry import out_size
        expected=out_size(source.shape[1]*int(spec.scale),source.shape[0]*int(spec.scale),*geometry)
        if expected!=(w*int(spec.scale),h*int(spec.scale)):
            raise ValueError("Grain source-sized crop rounding differs at requested delivery scale; choose scale 1 or pixel-aligned crop")
    out=upscale(full,Plan(h,w,int(spec.scale)),cancelled=cancelled)
    if float(spec.sharpen_amount)>0:
        out=unsharp_float_bands_np(out,radius=float(spec.sharpen_radius),amount=float(spec.sharpen_amount),threshold=float(spec.sharpen_threshold))
    if not spec.float_output:
        maximum=65535 if bits==16 else 255
        out=np.rint(np.clip(out,0,1)*maximum).astype(np.uint16 if bits==16 else np.uint8)
    return out,{**stats,'w':out.shape[1],'h':out.shape[0],'px':out.shape[0]*out.shape[1],
                'scale':int(spec.scale),'photo_grain_delivery':'source-edit-then-resize-sharpen',
                'sharpen_amount':float(spec.sharpen_amount)}
