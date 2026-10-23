"""Non-AI photo detail v1. Ranges/defaults are original product choices, not official claims."""
from copy import deepcopy
import math
KEY = '_photo_detail'
ALGORITHM = 'lrt-photo-detail-v1'
NAMES = ('sharpen_amount','sharpen_radius','sharpen_detail','luma_amount','luma_detail','luma_contrast','chroma_amount','chroma_detail','chroma_smoothness')
IDS = dict(zip(NAMES, ('e9c7dd33a1','d0f17720d3','583a2e6a82','16888f9a2b','39567e3766','220c6c8d23','f91cc0b7ee','dbd69ac908','5b97b902d4')))
DEFAULTS = dict(zip(NAMES, (0.,1.,50.,0.,50.,50.,0.,50.,50.)))
def default():
    return {'version':1,'algorithm':ALGORITHM,'enabled':True,**DEFAULTS}
def check(value):
    if value is None:return default()
    if type(value) is not dict or set(value)!=set(default()):raise ValueError('Photo detail requires a complete v1 recipe')
    if type(value['version']) is not int or value['version']!=1 or value['algorithm']!=ALGORITHM or type(value['enabled']) is not bool:raise ValueError('Unsupported photo detail schema')
    result=deepcopy(value)
    for key in NAMES:
        lo,hi=(0.1,3.) if key=='sharpen_radius' else (0.,100.)
        v=value[key]
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError(f'{key} must be finite within [{lo},{hi}]')
        result[key]=float(v)
    return result
def active(value):
    s=check(value)
    return s['enabled'] and any(s[k]>0 for k in ('sharpen_amount','luma_amount','chroma_amount'))
def effective(value):
    s=check(value)
    return tuple(s[k] if s['enabled'] or not k.endswith('_amount') else 0. for k in NAMES)
def status(value):
    s=check(value)
    return {'spec':s,'active':active(s),'ai':False,'whole_frame_required':True,'algorithm':ALGORITHM,
            'limits':{k:{'min':0.1 if k=='sharpen_radius' else 0,'max':3 if k=='sharpen_radius' else 100,'default':DEFAULTS[k],'provenance':'original-product-range; official-unspecified'} for k in NAMES},
            'requirements':{k:'LNX-REF-PC-32455-C-'+v for k,v in IDS.items()}}
