"""Bounded proxy-stage extraction. No histogram maths and no full-image CPU copy."""
from dataclasses import dataclass
import math
import numpy as np

STAGES=('original','levels-input','curves-input','output')
MAX_SAMPLES=65536

@dataclass(frozen=True)
class Sample:
    pixels:np.ndarray
    width:int
    height:int
    grid_width:int
    grid_height:int


def grid_shape(width:int,height:int,budget:int=MAX_SAMPLES):
    if type(width) is not int or type(height) is not int or width<1 or height<1:
        raise ValueError('invalid scope dimensions')
    if type(budget) is not int or not 1<=budget<=MAX_SAMPLES:raise ValueError('invalid sample budget')
    if width*height<=budget:return width,height
    # Cover the entire spatial extent, including extremely wide/tall panoramas.
    gw=min(width,max(1,int(math.sqrt(budget*width/height))))
    gh=min(height,max(1,budget//gw))
    gw=min(width,budget//gh)
    return gw,gh


def gather(tensor,budget=MAX_SAMPLES):
    if tensor.ndim!=4 or tensor.shape[0]!=1 or tensor.shape[1]!=3:
        raise ValueError('scope sampling requires one NCHW RGB image')
    import torch
    height,width=map(int,tensor.shape[-2:]);gw,gh=grid_shape(width,height,budget)
    # Pairwise advanced indexing allocates only 3*gw*gh values on the device.
    # Do NOT index_select whole rows or copy the full tensor to CPU first.
    xs=((torch.arange(gw,device=tensor.device,dtype=torch.float64)+.5)*width/gw).floor().long()
    ys=((torch.arange(gh,device=tensor.device,dtype=torch.float64)+.5)*height/gh).floor().long()
    pixels=tensor[0,:,ys[:,None],xs[None,:]].permute(1,2,0)
    pixels=pixels.detach().to(device='cpu',dtype=torch.float32).contiguous().numpy().copy()
    return Sample(pixels,width,height,gw,gh)


def sample_stage(pipeline,stage,strength,channel,params):
    if stage not in STAGES:raise ValueError('unknown colour-scope stage')
    if stage=='original':return gather(pipeline.src_f32)
    captured=[]
    def tap(name,tensor):
        if name==stage:captured.append(gather(tensor))
    # This may update derived caches/timings but never packs or publishes a frame.
    # Full pipeline intermediates still require the normal renderer's memory budget.
    pipeline.retouch(strength,channel=channel,scope_tap=tap,**params)
    if len(captured)!=1:raise RuntimeError('requested colour stage was not produced exactly once')
    return captured[0]
