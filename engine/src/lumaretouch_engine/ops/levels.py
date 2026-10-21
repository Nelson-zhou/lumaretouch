"""Versioned display-sRGB levels. Neutral channels bypass clipping exactly.

Active channels explicitly clamp normalized input, apply gamma 1/g, then map
output endpoints. Reversed output endpoints intentionally support inversion.
Rust core/levels/levels.rs defines the matching validation/scalar reference.
"""
import math
import numpy as np
from ..optional_dependencies import optional_module

torch=optional_module('torch')
CHANNELS=('master','red','green','blue')
KEYS=('input_black','input_white','gamma','output_black','output_white')
MIN_GAP=1e-5
GAMMA_LIMITS=(.1,10.)
NEUTRAL=(0.,1.,1.,0.,1.)


def default_levels():
    return dict(version=1,space='srgb-display',enabled=True,
                **{channel:dict(zip(KEYS,NEUTRAL)) for channel in CHANNELS})


def check_levels(value):
    if value is None:return default_levels()
    if type(value) is not dict or set(value)!={'version','space','enabled',*CHANNELS}:
        raise ValueError('levels requires a complete versioned recipe')
    if type(value['version']) is not int or value['version']!=1 or value['space']!='srgb-display':
        raise ValueError('unsupported levels version or colour domain')
    if type(value['enabled']) is not bool:raise ValueError('levels enabled must be boolean')
    result=dict(version=1,space='srgb-display',enabled=value['enabled'])
    for channel in CHANNELS:
        row=value[channel]
        if type(row) is not dict or set(row)!=set(KEYS):raise ValueError('levels channel fields missing or unknown')
        if any(type(row[key]) not in (int,float) or not math.isfinite(row[key]) for key in KEYS):
            raise ValueError('levels parameters must be finite numbers')
        b,w,g,ob,ow=(float(row[key]) for key in KEYS)
        if any(not 0<=v<=1 for v in (b,w,ob,ow)) or w-b<MIN_GAP:
            raise ValueError('levels input endpoints need a positive gap >=1e-5 within [0,1]')
        if not GAMMA_LIMITS[0]<=g<=GAMMA_LIMITS[1]:raise ValueError('levels gamma must be in [0.1,10]')
        result[channel]=dict(zip(KEYS,(b,w,g,ob,ow)))
    return result


def parameters(value):
    spec=check_levels(value)
    return tuple(None if not spec['enabled'] or tuple(spec[c][k] for k in KEYS)==NEUTRAL
                 else tuple(spec[c][k] for k in KEYS) for c in CHANNELS)


def is_identity(value):return all(p is None for p in parameters(value))


def _apply_np(x,p):
    if p is None:return x
    b,w,g,ob,ow=p
    return ob+(ow-ob)*np.clip((x-b)/(w-b),0.,1.)**(1./g)


def levels_np(rgb,spec):
    p=parameters(spec)
    if all(v is None for v in p):return rgb
    if rgb.shape[-1]!=3 or not np.issubdtype(rgb.dtype,np.floating):raise ValueError('levels expects floating RGB')
    return np.stack([_apply_np(_apply_np(rgb[...,i],p[0]),p[i+1]) for i in range(3)],axis=-1)


def _apply_t(x,p):
    if p is None:return x
    b,w,g,ob,ow=p
    return ob+(ow-ob)*((x-b)/(w-b)).clamp(0.,1.).pow(1./g)


def levels_t(rgb,p):
    if all(v is None for v in p):return rgb
    if rgb.ndim!=4 or rgb.shape[1]!=3:raise ValueError('levels expects NCHW RGB')
    return torch.stack([_apply_t(_apply_t(rgb[:,i],p[0]),p[i+1]) for i in range(3)],dim=1)
