"""Owned semantic smoothing input; existing guided-band solver stays unchanged.

Contexts are ephemeral frozen export evidence, never persisted model rasters.
Original-file provenance remains distinct from canonical composite identity.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math
import numpy as np

PARAMS={'radius':(1,256),'eps':(1e-6,1.),'texture_radius':(1,32),
        'detail_gain':(0.,2.),'mid_gain':(0.,2.),'broad_gain':(0.,2.)}
INTEGERS=frozenset(('radius','texture_radius'))


def _hash(value):
    result=sha256()
    for row in value:result.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return result.hexdigest()


def _read(owner,public,private,default=None):
    if isinstance(owner,dict):
        return owner.get(public,owner.get(private,default))
    return getattr(owner,private,default)


def check_recipe(value):
    from .semantic_sources import SOURCE_LABELS
    if type(value) is not dict or set(value)!={'strength','channel','params'}:
        raise ValueError('Smoothing needs its exact strength/channel/parameter recipe')
    strength=value['strength'];channel=value['channel'];params=value['params']
    if type(strength) not in (int,float) or not math.isfinite(strength) or not 0<=strength<=1:
        raise ValueError('Smoothing strength must be finite and within [0,1]')
    if channel is not None and (type(channel) is not str or channel not in SOURCE_LABELS):
        raise ValueError('Smoothing channel has no owned semantic source consumer')
    if type(params) is not dict or set(params)!=set(PARAMS):
        raise ValueError('Smoothing requires all existing solver parameters')
    for key,(lo,hi) in PARAMS.items():
        number=params[key]
        if (type(number) not in (int,float) or not math.isfinite(number) or not lo<=number<=hi
                or key in INTEGERS and (type(number) is not int)):
            raise ValueError('Invalid existing smoothing parameter: '+key)
    return deepcopy(value)


def recipe(owner,overrides=None):
    value={'strength':_read(owner,'strength','_strength',0.),
           'channel':_read(owner,'channel','_channel'),
           'params':dict(_read(owner,'params','_params',{}))}
    if overrides is not None:
        if 'value' in overrides:value['strength']=overrides['value']
        if 'channel' in overrides:value['channel']=overrides['channel'] or None
        for key in PARAMS:
            if overrides.get(key) is not None:value['params'][key]=overrides[key]
    return check_recipe(value)


def _provenance(owner,path):
    from . import local_mask_state as M
    stamp=M.file_stamp(path)
    if not isinstance(owner,dict):
        row=owner._docs[owner._doc_index]
        if row.get('_local_source_stamp')!=stamp:
            raise ValueError('Smoothing original-file provenance changed after decoding')
    result=M.source_digest(path)
    if M.file_stamp(path)!=stamp:raise ValueError('Smoothing provenance changed during capture')
    return result


def capture(owner,path=None,recipe_value=None):
    from . import creative_derived_source as D,local_mask_state as M
    from .creative_document_host import memory_budget
    value=recipe(owner) if recipe_value is None else check_recipe(recipe_value)
    if value['strength']==0 and value['channel'] is None:return None
    source=D.binding(owner);channel=value['channel']
    if path is None and not isinstance(owner,dict):path=owner._doc_path
    if not path:raise ValueError('Smoothing requires original-file provenance')
    proof=model=mask=digest=None
    if channel is not None:
        pc=_read(owner,'precompute','_precompute')
        if pc is None or getattr(pc,'backend',None)!='mediapipe':
            raise ValueError('Smoothing requires measured current-source semantic analysis')
        D.verify_precompute(owner,pc)
        model=M.semantic_owner(pc,pc.backend)
        if model is None:raise ValueError('Smoothing semantic model identity is missing')
        raw=np.asarray((getattr(pc,'masks',{}) or {}).get(channel))
        if raw.dtype.kind!='f' or raw.ndim!=2 or not np.isfinite(raw).all() or np.any(raw<0) or np.any(raw>1):
            raise ValueError('Smoothing semantic coverage is missing or invalid')
        if raw.size*8+8_388_608>memory_budget():raise ValueError('Smoothing evidence exceeds memory budget')
        mask=np.array(raw,dtype=np.float32,copy=True);mask.setflags(write=False)
        proof=deepcopy(pc.input_source_binding);digest=_hash(mask)
    context={'version':1,'source':source,'original_sha256':_provenance(owner,path),
             'recipe':value,'analysis':proof,'semantic_owner':model,'mask':mask,'mask_sha256':digest}
    return verify_context(context,source)


def verify_context(context,source,path=None):
    from . import creative_derived_masks as C
    keys={'version','source','original_sha256','recipe','analysis','semantic_owner','mask','mask_sha256'}
    if (type(context) is not dict or set(context)!=keys or type(context['version']) is not int
            or context['version']!=1 or context['source']!=source):
        raise ValueError('Smoothing lacks exact immutable source evidence')
    value=check_recipe(context['recipe']);channel=value['channel']
    fields={} if channel is None else {channel:context['mask']}
    hashes={} if channel is None else {channel:context['mask_sha256']}
    C.verify_context({'version':1,'source':source,'original_sha256':context['original_sha256'],
        'analysis':context['analysis'],'semantic_owner':context['semantic_owner'],
        'fields':fields,'field_sha256':hashes},source,path=path)
    if channel is not None and value['strength']!=0 and not np.any(context['mask']>0):
        raise ValueError('Smoothing selected semantic field contains no editable support')
    if channel is None and (context['mask'] is not None or context['mask_sha256'] is not None):
        raise ValueError('Unmasked smoothing cannot retain a hidden mask')
    return context


def verify_snapshot(snapshot,path=None):
    from . import creative_derived_source as D
    if D.record(snapshot) is None:return None
    strength=_read(snapshot,'strength','_strength',0.)
    channel=_read(snapshot,'channel','_channel')
    if type(strength) in (int,float) and strength==0 and channel is None:
        if snapshot.get('creative_smoothing_context') is not None:
            raise ValueError('Neutral unmasked smoothing cannot retain stale context')
        return None
    value=recipe(snapshot)
    context=verify_context(snapshot.get('creative_smoothing_context'),D.binding(snapshot),path)
    if context['recipe']!=value:raise ValueError('Smoothing recipe changed after evidence capture')
    return context


def preview(engine,recipe_value=None):
    from .creative_derived_repair_runtime import verify_pipeline
    from .creative_derived_repairs import stack_digest
    context=capture(engine,recipe_value=recipe_value);pipe=engine._vram
    if context is None:raise ValueError('Neutral unmasked smoothing has no active consumer context')
    evidence=verify_pipeline(pipe,context['source'])
    if evidence['stack_sha256']!=stack_digest(engine):raise ValueError('Smoothing repair history differs from current document')
    pixels=pipe.base()[0].permute(1,2,0).detach().cpu().numpy()
    expected=evidence['output'] or evidence['input']
    if list(pixels.shape)!=expected['shape'] or _hash(pixels)!=expected['sha256']:
        raise ValueError('Smoothing pixels differ from owned repair replay')
    channel=context['recipe']['channel']
    if channel is not None:
        actual=pipe.mask(channel).detach().cpu().numpy()
        if actual.dtype!=np.float32 or actual.shape!=(1,1,*context['mask'].shape) or not np.array_equal(actual[0,0],context['mask']):
            raise ValueError('Installed smoothing mask differs from measured current-source evidence')
    key=(json.dumps(context['source'],sort_keys=True),json.dumps(context['analysis'],sort_keys=True),
         json.dumps(context['semantic_owner'],sort_keys=True),context['mask_sha256'],
         evidence['stack_sha256'],expected['sha256'],context['original_sha256'])
    from .creative_derived_smoothing_runtime import bind
    bind(pipe,context['source'],pixels,mask_channel=channel,mask_pixels=context['mask'],
         domain='preview',evidence_key=key)
    return context,pixels,key


def require_command(engine,request):
    if (type(request) is not dict or request.get('cmd')!='set_strength'
            or set(request)-{'cmd','value','channel',*PARAMS}):
        raise ValueError('Invalid derived smoothing command envelope')
    if 'channel' in request and request['channel'] is not None and type(request['channel']) is not str:
        raise ValueError('Smoothing channel must be an explicit source name or null')
    value=recipe(engine,request)
    if value['strength']!=0:preview(engine,value)
    return value


def configure_export(spec,snapshot,h,w):
    from .export import resample_field
    context=verify_snapshot(snapshot)
    spec.creative_smoothing_context=context
    if context is None:
        spec.channel=None;spec._creative_smoothing_resampled=None
        return
    source=context['source']
    if (h,w)!=(source['height'],source['width']):
        raise ValueError('Smoothing export must use the immutable source grid')
    channel=context['recipe']['channel']
    spec.channel=channel
    if channel is not None:
        spec.mask_names=[channel]
        spec.masks=resample_field(context['mask'][None],(h,w))
        spec._creative_smoothing_resampled=(_hash(spec.masks),tuple(spec.masks.shape),channel)
    else:
        spec._creative_smoothing_resampled=None


def _spec_recipe(spec):
    return check_recipe({'strength':spec.strength,'channel':spec.channel,
                         'params':{key:getattr(spec,key) for key in PARAMS}})


def _proof(spec,pixels):
    from . import creative_derived_source as D
    from .creative_derived_repair_export import _pixels
    source=D.binding({'creative_base':spec.creative_base})
    context=verify_context(spec.creative_smoothing_context,source)
    if context['recipe']!=_spec_recipe(spec):raise ValueError('Smoothing export recipe changed after capture')
    return (source['sha256'],_pixels(source,pixels),json.dumps(context['recipe'],sort_keys=True),
            context['mask_sha256'],json.dumps(context['analysis'],sort_keys=True),
            json.dumps(context['semantic_owner'],sort_keys=True))


def stamp_pixels(spec,pixels):
    """INTERNAL: only after canonical full-float source resolution."""
    spec._creative_smoothing_pixels=_proof(spec,pixels)


def verify_export(spec,source,base,divisor):
    if divisor!=1. or getattr(spec,'_creative_smoothing_pixels',None)!=_proof(spec,source):
        raise ValueError('Smoothing export does not own these full-float source pixels')
    if spec.channel is not None:
        if (spec.mask_names!=[spec.channel] or type(spec.masks) is not np.ndarray
                or spec.masks.dtype!=np.float32 or tuple(spec.masks.shape)!=(1,*source.shape[:2])
                or not np.isfinite(spec.masks).all() or np.any(spec.masks<0) or np.any(spec.masks>1)
                or getattr(spec,'_creative_smoothing_resampled',None)!=(_hash(spec.masks),tuple(spec.masks.shape),spec.channel)):
            raise ValueError('Smoothing full-resolution mask changed after owned resampling')
    if getattr(spec,'repair',[]):
        from .creative_derived_repair_export import verify_replayed
        if base is None:raise ValueError('Smoothing lost its ordered repair replay')
        verify_replayed(spec,base)
        return base
    if base is not None:raise ValueError('Smoothing received an unowned replacement base')
    return source


def recovery_context(engine):
    context,_,key=preview(engine)
    return {'version':1,'source':deepcopy(context['source']),'recipe':deepcopy(context['recipe']),
            'evidence_key':list(key)}
