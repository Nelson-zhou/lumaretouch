"""Reviewed normalized brush intent for the existing deterministic heal solver.

This is not neural/generative inpainting. Coverage is rerasterized from vectors;
proxy coverage is diagnostic only. Solver context scales with its captured grid.
"""
import math
import numpy as np
from . import clone_stamp as C

VERSION='heal-vector-v1'


def check_recipe(raw):
    keys={'version','points','axes','hardness','opacity','reference_size','solver'}
    if type(raw) is not dict or set(raw)!=keys or raw['version']!=VERSION:
        raise ValueError('Unsupported heal-vector recipe')
    clone=C.check_recipe({k:raw[k] for k in ('points','axes','hardness','opacity')} |
                         {'version':C.VERSION,'offset':[0.,0.]})
    size=raw['reference_size']
    if (not isinstance(size,(list,tuple)) or len(size)!=2 or
            any(type(n) is not int or n<1 for n in size) or size[0]*size[1]>120_000_000):
        raise ValueError('Invalid heal reference grid')
    from ..repair_record import DEFAULT_REPAIR, check_repair_params
    if type(raw['solver']) is not dict or set(raw['solver'])!=set(DEFAULT_REPAIR):
        raise ValueError('Heal vector must retain its complete solver contract')
    solver=check_repair_params('heal',raw['solver'])
    return {'version':VERSION,**{k:clone[k] for k in ('points','axes','hardness','opacity')},
            'reference_size':list(size),'solver':solver}


def _brush(recipe):
    p=check_recipe(recipe)
    return {k:p[k] for k in ('points','axes','hardness','opacity')} | {'version':C.VERSION,'offset':[0.,0.]}


def raster_plan(shape,recipe):
    """Bound coverage and expanded solver context before allocating either."""
    p=check_recipe(recipe)
    if (not isinstance(shape,(tuple,list)) or len(shape)!=2 or
            any(type(n) is not int or n<1 for n in shape)):
        raise ValueError('Invalid heal replay grid')
    h,w=shape
    _,_,bounds,_=C.raster_plan(shape,_brush(p))
    y0,y1,x0,x1=bounds
    # Retained pad is in reference proxy pixels, not accidentally final pixels.
    pad=math.ceil(p['solver']['pad']*min(h,w)/min(p['reference_size']))
    margin=int(max(pad,p['solver']['grow']*max(y1-y0-1,x1-x0-1)/2.))
    box=(max(0,y0-margin),min(h,y1+margin),max(0,x0-margin),min(w,x1+margin))
    if (box[1]-box[0])*(box[3]-box[2])>C.MAX_ROI:
        raise ValueError('Heal solver context exceeds the local raster budget; split the stroke')
    return p,pad,box


def admit_memory(shape,recipe):
    """Read current memory policy for capture and replay, never reduce context."""
    from ..cpu_memory_budget import available_estimate
    p,pad,box=raster_plan(shape,recipe)
    h,w=shape;area=(box[1]-box[0])*(box[3]-box[2])
    if h*w*24+area*128+8_388_608>available_estimate():
        raise ValueError("Heal replay exceeds available bounded memory")
    return p,pad,box


def apply_t(cur,recipe):
    """Read from the preceding float32 result; commit only after complete replay."""
    import torch
    from .inpaint import inpaint_t,levels_for,hole_extent,crop_apply_t
    if not isinstance(cur,torch.Tensor) or cur.ndim!=4 or cur.shape[:2]!=(1,3) or cur.dtype!=torch.float32:
        raise ValueError('Heal vector requires float32 BCHW RGB')
    h,w=map(int,cur.shape[-2:]);p,pad,planned=raster_plan((h,w),recipe)
    if p['opacity']==0:return cur,None
    # Full output plus local float masks, pyramids, diffusion work and transfers.
    p,pad,planned=admit_memory((h,w),p)
    coverage,bounds=C.raster((h,w),_brush(p))
    ys,xs=np.nonzero(coverage>0)
    if not len(ys):raise ValueError('Heal stroke covers no pixels')
    by0,_,bx0,_=bounds
    margin=int(max(pad,p['solver']['grow']*max(int(ys.max()-ys.min()),int(xs.max()-xs.min()))/2.))
    box=(max(0,by0+int(ys.min())-margin),min(h,by0+int(ys.max())+1+margin),
         max(0,bx0+int(xs.min())-margin),min(w,bx0+int(xs.max())+1+margin))
    y0,y1,x0,x1=box
    weight=np.zeros((y1-y0,x1-x0),np.float32)
    ay0,ay1=max(y0,bounds[0]),min(y1,bounds[1]);ax0,ax1=max(x0,bounds[2]),min(x1,bounds[3])
    weight[ay0-y0:ay1-y0,ax0-x0:ax1-x0]=coverage[ay0-by0:ay1-by0,ax0-bx0:ax1-bx0]
    sub=cur[...,y0:y1,x0:x1]
    if not bool(torch.isfinite(sub).all()) or bool(torch.any(sub<0)) or bool(torch.any(sub>1)):
        raise ValueError('Deterministic heal supports finite SDR pixels, not clipped HDR')
    mask=torch.from_numpy(weight[None,None]).to(cur.device)
    fill=inpaint_t(sub,mask,levels=levels_for(hole_extent(weight),y1-y0,x1-x0),
        smooth_iters=p['solver']['smooth_iters'],refine_iters=p['solver']['refine_iters'],kappa=p['solver']['kappa'])
    return crop_apply_t(cur,box,fill),box
