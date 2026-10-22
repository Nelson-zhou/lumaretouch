"""Actual pre-consumer stage inputs; no inverse of an 8-bit display readout."""
from .color_action_sampling import Projection, admit, available_memory, gather_region, _region
from .color_action_readiness import require_warm_prefix
from .ops import curves as C
from .color_picker_math import selection


def stage_name(action,channel):
    selection(action,channel)
    return 'levels-input' if action.startswith('levels_') else 'hsl-input' if action=='hsl' else 'curve-'+channel+'-input'


def stage(pipeline,spec,strength,channel,params,action,curve_channel):
    selection(action,curve_channel)
    if Projection.from_pipeline(pipeline)!=spec:raise ValueError('Color picker geometry changed')
    admit(spec,available_memory(pipeline.device));require_warm_prefix(pipeline,strength,params)
    out=pipeline.retouch(strength,channel=channel,render_stage='wb-input',**params)
    out=pipeline.apply_exposure(out)
    if action.startswith('levels_'):return out
    out=pipeline.apply_levels(out)
    if action=='hsl':return pipeline.apply_curves(out)
    # Same ordering, transfer functions and compiled coefficients as curves_t.
    bundles=pipeline.curves_compiled
    if len(bundles)==6:out=C.P.evaluate_t(out,bundles[5])
    if curve_channel=='master':return out
    import torch
    out=torch.stack([C._eval_t(out[:,i],bundles[0]) for i in range(3)],dim=1)
    if curve_channel!='luminance':return out
    return torch.stack([C._eval_t(out[:,i],bundles[i+1]) for i in range(3)],dim=1)


def projected(pipeline,spec,strength,channel,params,action,curve_channel):
    import torch
    out=stage(pipeline,spec,strength,channel,params,action,curve_channel)
    if tuple(out.shape)!=(1,3,spec.height,spec.width) or not out.is_floating_point() or not torch.isfinite(out).all():raise ValueError('Invalid targeted color input stage')
    # Encoded-sRGB resampling matches the retained display-referred consumer
    # semantics. Float values are sampled before RGBA8 presentation quantization.
    out=spec.apply(out)
    if Projection.from_pipeline(pipeline)!=spec:raise ValueError('Color picker geometry changed during render')
    return out


def sample(pipeline,spec,strength,channel,params,action,curve_channel,region):
    _region(region,spec)
    import torch
    out=projected(pipeline,spec,strength,channel,params,action,curve_channel)
    rows=gather_region(out,region,spec)
    coverage=gather_region(spec.apply(torch.ones_like(out[:,:1])),region,spec)
    return tuple(tuple(pixel+[cover[0]]) for pixel,cover in zip(rows,coverage))
