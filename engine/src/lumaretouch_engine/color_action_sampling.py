"""WB-input projection and small-region extraction, never a display-RGB inverse.

This module owns geometry/resource validation only. The action controller must also
bind document, recipe revision and a natively acknowledged presented capture.
"""
from dataclasses import dataclass
from .ops import geometry as G
from .ops.exposure import _lin_t, _slin_t
from .geometry_projection import project
from .color_action_readiness import require_warm_prefix

PROJECTION_VERSION = 'crop-rotate-fixed-proxy-v1'
MAX_SOURCE_PIXELS = 8*1024*1024
MAX_ROTATION_PIXELS = 32*1024*1024
MAX_TRANSIENT_BYTES = 8*1024**3
MAX_CAPTURE_BYTES = 128*1024**2


@dataclass(frozen=True)
class Projection:
    width: int
    height: int
    rect: tuple[float,float,float,float]
    rotation: float
    integer_crop: tuple[int,int,int,int]
    rotated: tuple[int,int]

    @classmethod
    def from_pipeline(cls, pipeline):
        width, height = pipeline.w, pipeline.h
        if type(width) is not int or type(height) is not int or width<1 or height<1:
            raise ValueError('Invalid WB input dimensions')
        x0,y0,x1,y1,rotation = G.check(pipeline.crop_rect,pipeline.crop_rotation)
        rect = (x0,y0,x1,y1)
        xa,xb = G._cut(width,x0,x1); ya,yb = G._cut(height,y0,y1)
        return cls(width,height,rect,rotation,(xa,ya,xb, yb),G.out_size(width,height,rect,rotation))

    def descriptor(self):
        return {'version':PROJECTION_VERSION,'source_proxy':[self.width,self.height],
                'rect':list(self.rect),'integer_crop':list(self.integer_crop),'rotation':self.rotation,
                'quarter_turn':G._snapped_quarter_turn(self.rotation),'rotated':list(self.rotated),
                'target':[self.width,self.height],'resize':'bilinear','align_corners':False,'antialias':False}

    def apply(self, tensor):
        return project(tensor,self.rect,self.rotation,(self.width,self.height))


def transient_estimate(spec):
    # Projection allocation estimate, not a measured total renderer peak. Includes live input,
    # decoder/encoder branches, resize/packing, binary64 singleton coordinates,
    # int64 indices, four neighbours and intermediate RGB tensors. Coverage/risk
    # projections run sequentially, not as extra resident full-image channels.
    n = spec.width*spec.height; r = spec.rotated[0]*spec.rotated[1]
    return 128*n + 384*r + 1024*1024


def admit(spec, available_bytes):
    n = spec.width*spec.height; r = spec.rotated[0]*spec.rotated[1]
    if n>MAX_SOURCE_PIXELS or r>MAX_ROTATION_PIXELS or n*4>MAX_CAPTURE_BYTES:
        raise ValueError('WB input projection exceeds the raster budget; use a smaller proxy')
    if type(available_bytes) is not int or available_bytes<=0:
        raise ValueError('Available memory could not be established for WB sampling')
    planned = transient_estimate(spec)
    # Leave explicit headroom; admission cannot guarantee concurrent allocations.
    usable = max(0,available_bytes-256*1024**2)*65//100
    if planned>MAX_TRANSIENT_BYTES or planned>usable:
        raise ValueError('WB input projection exceeds available memory; use a smaller proxy')
    return planned


def available_memory(device):
    if device.type!='cpu':
        import torch
        return int(torch.cuda.mem_get_info(device)[0])
    from .cpu_memory_budget import available_estimate
    return available_estimate()



def _same(pipeline,spec):
    if Projection.from_pipeline(pipeline)!=spec:
        raise ValueError('WB input geometry changed; capture again')


def _input(pipeline,spec,strength,channel,params,available):
    _same(pipeline,spec)
    admit(spec,available_memory(pipeline.device) if available is None else available)
    require_warm_prefix(pipeline,strength,params)
    import torch
    stage = pipeline.retouch(strength,channel=channel,render_stage='wb-input',**params)
    if tuple(stage.shape)!=(1,3,spec.height,spec.width) or not stage.is_floating_point():
        raise ValueError('WB input stage shape or dtype changed')
    if not torch.isfinite(stage).all():
        raise ValueError('WB input contains invalid encoded RGB')
    _same(pipeline,spec)
    return stage


def preview(pipeline,spec,strength,channel,params,*,available=None):
    stage = _input(pipeline,spec,strength,channel,params,available)
    result = _slin_t(spec.apply(_lin_t(stage)))
    _same(pipeline,spec)
    return result


def _region(region,spec):
    if type(region) is not dict or set(region)!={'x','y','width','height'}:
        raise ValueError('Invalid WB sample region')
    x,y,w,h = (region[k] for k in ('x','y','width','height'))
    if any(type(v) is not int for v in (x,y,w,h)) or x<0 or y<0 or w<1 or h<1 or w*h>121:
        raise ValueError('Invalid WB sample region')
    if x+w>spec.width or y+h>spec.height:
        raise ValueError('WB sample region exceeds its captured image')
    return x,y,w,h


def gather_region(tensor,region,spec):
    x,y,w,h = _region(region,spec)
    if tensor.ndim!=4 or tensor.shape[0]!=1 or tensor.shape[1] not in (1,3) or tuple(tensor.shape[-2:])!=(spec.height,spec.width):
        raise ValueError('WB projected sample shape changed')
    import torch
    # Slice on device first. Only 1–121 pixels per channel cross to the CPU.
    small=tensor[0,:,y:y+h,x:x+w].permute(1,2,0).reshape(-1,tensor.shape[1])
    return small.detach().to(device='cpu',dtype=torch.float64).tolist()


def sample(pipeline,spec,strength,channel,params,region,*,available=None):
    _region(region,spec)
    stage = _input(pipeline,spec,strength,channel,params,available)
    import torch
    rgb = gather_region(spec.apply(_lin_t(stage)),region,spec)
    coverage = gather_region(spec.apply(torch.ones_like(stage[:,:1])),region,spec)
    # Test clipping before geometry/averaging, so interpolation cannot hide one
    # clipped source contribution. This detects working-stage saturation, not RAW.
    source_risk = ((stage>=1.0)|(stage<0.0)).any(dim=1,keepdim=True).to(dtype=stage.dtype)
    risk = gather_region(spec.apply(source_risk),region,spec)
    _same(pipeline,spec)
    return tuple(tuple(pixel+[cover[0],bad[0]]) for pixel,cover,bad in zip(rgb,coverage,risk))
