# SPDX-License-Identifier: AGPL-3.0-only
# Original work: Chris Cork, RapidRetouch. See ../third_party/rapidretouch/NOTICE.
# Adapted for LumaRetouch on2026-10-22: validation, bounded source context,
# explicit failures and exact preservation outside the actual affected region.
"""Independent source-sampled patch, not an alias for automatic spot healing.

Copies source texture while reconstructing target low-frequency lighting in
linear sRGB. The source is the current pre-light repair base, including earlier
repair operations. Parameters store normalized polygon/offset, not result pixels.
"""
import math
import numpy as np
from ..optional_dependencies import optional_module
from ..third_party.rapidretouch.patch_filters import masked_blur
from .exposure import _lin_np, _slin_np

cv2 = optional_module('cv2')
VERSION = 'source-patch-v1'
MAX_POINTS = 256
FEATHER = 0.08
TONE_SCALE = 0.25


def _number(value):
    if type(value) not in (int,float):
        raise ValueError('Patch coordinates must be finite numbers')
    try:
        value=float(value)
    except (OverflowError,ValueError) as error:
        raise ValueError('Patch coordinate is not finite') from error
    if not math.isfinite(value):
        raise ValueError('Patch coordinate is not finite')
    return value


def check_recipe(raw):
    if type(raw) is not dict or set(raw)!={'version','polygon','offset'} or raw['version']!=VERSION:
        raise ValueError('Unsupported source-patch recipe')
    polygon=raw['polygon'];offset=raw['offset']
    if not isinstance(polygon,(list,tuple)) or not 3<=len(polygon)<=MAX_POINTS:
        raise ValueError('Patch selection requires 3–256 vertices')
    clean=[]
    for point in polygon:
        if not isinstance(point,(list,tuple)) or len(point)!=2:
            raise ValueError('Invalid patch selection vertex')
        x,y=map(_number,point)
        if not 0<=x<=1 or not 0<=y<=1:
            raise ValueError('Patch selection is outside the image')
        clean.append([x,y])
    if not isinstance(offset,(list,tuple)) or len(offset)!=2:
        raise ValueError('Patch source offset requires two coordinates')
    dx,dy=map(_number,offset)
    if not -1<=dx<=1 or not -1<=dy<=1:
        raise ValueError('Patch source offset is outside the image')
    if any(not 0<=x+dx<=1 or not 0<=y+dy<=1 for x,y in clean):
        raise ValueError('Patch source selection is outside the image')
    return {'version':VERSION,'polygon':clean,'offset':[dx,dy]}


def selection_mask(shape,polygon,box=None):
    if cv2 is None:
        raise RuntimeError('Source patch requires the packaged OpenCV runtime')
    h,w=shape
    y0,y1,x0,x1=(0,h,0,w) if box is None else box
    if (y1-y0)*(x1-x0)>16_000_000:
        raise ValueError('Patch selection/context exceeds its local raster budget')
    # Quantize once on the global1/16-pixel lattice, then translate by integers.
    # Local rasterization must not choose different rounding at large image x/y.
    points=np.rint((np.asarray([[x*w,y*h] for x,y in polygon],np.float64)-.5)*16).astype(np.int64)
    points-=np.asarray([x0*16,y0*16],np.int64)
    mask=np.zeros((y1-y0,x1-x0),np.uint8)
    cv2.fillPoly(mask,[points.astype(np.int32)],1,lineType=cv2.LINE_AA,shift=4)
    return mask.astype(np.float32)


def _plan(shape, recipe):
    clean=check_recipe(recipe)
    if cv2 is None:
        raise RuntimeError('Source patch requires the packaged OpenCV runtime')
    h,w=shape
    if h<1 or w<1 or h*w>120_000_000:
        raise ValueError('Source patch image exceeds its raster limit')
    points=clean['polygon']
    # Rasterize only a small selection extent; a100MP source must not allocate a
    #100MP mask plus two full-size nonzero index arrays for a small facial patch.
    mx0=max(0,math.floor(min(x for x,y in points)*w)-2)
    mx1=min(w,math.ceil(max(x for x,y in points)*w)+3)
    my0=max(0,math.floor(min(y for x,y in points)*h)-2)
    my1=min(h,math.ceil(max(y for x,y in points)*h)+3)
    mask=selection_mask((h,w),points,(my0,my1,mx0,mx1))
    ys,xs=np.nonzero(mask);ys=ys+my0;xs=xs+mx0
    if not ys.size:
        raise ValueError('Patch selection contains no source pixels')
    dx,dy=(round(clean['offset'][0]*w),round(clean['offset'][1]*h))
    if dx==0 and dy==0:
        return (my0,my1,mx0,mx1), (0,0), None, None, 0
    if xs.min()+dx<0 or xs.max()+dx>=w or ys.min()+dy<0 or ys.max()+dy>=h:
        raise ValueError('Rasterized patch source selection exceeds the image')
    size=max(int(ys.max()-ys.min()),int(xs.max()-xs.min()),4)
    pad=round(size*.6)+4
    # Use a common context window rather than silently doing nothing when only
    # the requested padding, not the actual source selection, meets an edge.
    y0=max(0,int(ys.min())-pad,-dy);y1=min(h,int(ys.max())+pad+1,h-dy)
    x0=max(0,int(xs.min())-pad,-dx);x1=min(w,int(xs.max())+pad+1,w-dx)
    sel=selection_mask((h,w),points,(y0,y1,x0,x1))
    ring=np.clip(cv2.dilate(sel,np.ones((3,3),np.uint8),iterations=max(1,round(.15*size)))-sel,0,1)
    context=np.clip(ring+1-cv2.dilate(sel,np.ones((3,3),np.uint8),iterations=max(1,round(.3*size))),0,1)
    if np.count_nonzero(context)<4:
        raise ValueError('Patch needs surrounding target pixels to estimate lighting')
    return (y0,y1,x0,x1),(dx,dy),sel,context,size


def _render(target_window, source_window, sel, context, size):
    if not np.isfinite(target_window).all() or not np.isfinite(source_window).all():
        raise ValueError('Source patch input region contains nonfinite values')
    if sel is None:
        return target_window.copy()
    target=_lin_np(target_window).astype(np.float32)
    source=_lin_np(source_window).astype(np.float32)
    sigma=max(1.,TONE_SCALE*size)
    target_tone=masked_blur(target,context,sigma)
    source_tone=cv2.GaussianBlur(source,(0,0),sigma)
    healed=np.clip(target_tone*(source/np.maximum(source_tone,1e-4)),0,1)
    soft=cv2.GaussianBlur(sel,(0,0),max(.7,FEATHER*size))[...,None]
    result=_slin_np(np.clip(soft*healed+(1-soft)*target,0,1)).astype(np.float32)
    if not np.isfinite(result).all():
        raise ValueError('Source patch produced nonfinite values')
    out=target_window.copy()
    affected=soft[...,0]>0
    out[affected]=result[affected]
    return out


def apply(rgb,recipe):
    """CPU reference; validates only the selected/context regions, owns output."""
    if not isinstance(rgb,np.ndarray) or rgb.ndim!=3 or rgb.shape[2]!=3 or rgb.dtype!=np.float32:
        raise ValueError('Source patch requires float32 HWC RGB')
    box,(dx,dy),sel,context,size=_plan(rgb.shape[:2],recipe)
    y0,y1,x0,x1=box
    result=_render(rgb[y0:y1,x0:x1],rgb[y0+dy:y1+dy,x0+dx:x1+dx],sel,context,size)
    out=rgb.copy();out[y0:y1,x0:x1]=result
    return out


def apply_t(cur,recipe):
    """Production BCHW adapter: transfer only source/target ROI, never the frame.

    The resident float32 input is immutable; replacement is allocated on its
    original device only after the local algorithm has completed successfully.
    """
    import torch
    if not isinstance(cur,torch.Tensor) or cur.ndim!=4 or cur.shape[:2]!=(1,3) or cur.dtype!=torch.float32:
        raise ValueError('Source patch requires single float32 BCHW RGB')
    box,(dx,dy),sel,context,size=_plan(tuple(cur.shape[-2:]),recipe)
    y0,y1,x0,x1=box
    def local(y,x):
        return cur[0,:,y:y+y1-y0,x:x+x1-x0].detach().permute(1,2,0).contiguous().cpu().numpy()
    target=local(y0,x0)
    source=target if sel is None else local(y0+dy,x0+dx)
    result=_render(target,source,sel,context,size)
    if sel is None:
        return cur.clone(),None
    replacement=torch.from_numpy(result).permute(2,0,1).to(device=cur.device)
    out=cur.clone();out[0,:,y0:y1,x0:x1]=replacement
    return out,box
