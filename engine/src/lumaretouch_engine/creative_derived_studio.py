"""Owned pre-repair studio measurements on an immutable creative source.

The existing studio operator measures ``src_f32`` before repair, then adds its
contribution after repair/light, smoothing and fabric in the production chain.
This adapter preserves both boundaries. It does not substitute ``pipe.base()``,
resize a proxy semantic mask for export, or change the studio numerical solver.
Contexts are ephemeral snapshot evidence, never persisted model/output rasters.
"""
from copy import deepcopy
from hashlib import sha256
import json
import numpy as np


def _json(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def _hash(value):
    result=sha256()
    for row in value:result.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return result.hexdigest()


def _read(owner,public,private,default=None):
    if isinstance(owner,dict):
        if public in owner and private in owner:
            raise ValueError('Studio state contains ambiguous '+public+' aliases')
        return owner.get(public,owner.get(private,default))
    return getattr(owner,private,default)


def _source(owner):
    from . import creative_derived_source as D
    if isinstance(owner,dict):_read(owner,'creative_base','_creative_base')
    if D.record(owner) is None:raise ValueError('Studio evidence requires an immutable creative source')
    return D.binding(owner)


def _value(owner):
    from . import studio_background_state as S
    return S.check(_read(owner,'studio_background','_studio_background'))


def validate(value,source):
    """Validate durable intent even when every effect is currently disabled."""
    from . import studio_background_state as S
    from .creative_derived_repairs import check_binding
    source=check_binding(source)
    if source is None:raise ValueError('Studio intent needs an immutable source extent')
    value=S.check(value)
    if value['source'] is not None and value['source']!=source:
        raise ValueError('Studio regions or recovery strokes belong to another effective source')
    S.validate_budget(value,(source['height'],source['width']))
    return value


def validate_state(owner):
    """Pure durable validation for project/history, without model inference."""
    from . import creative_derived_source as D
    if isinstance(owner,dict):_read(owner,'creative_base','_creative_base')
    value=_value(owner)
    return value if D.record(owner) is None else validate(value,_source(owner))


def recipe_digest(value):
    from . import studio_background_state as S
    return sha256(_json(S.check(value)).encode('utf-8')).hexdigest()


def _provenance(owner,path):
    from . import local_mask_state as M
    stamp=M.file_stamp(path)
    if not isinstance(owner,dict):
        row=owner._docs[owner._doc_index]
        if row.get('_local_source_stamp')!=stamp:
            raise ValueError('Studio original-file provenance changed after decoding')
    digest=M.source_digest(path)
    if M.file_stamp(path)!=stamp:raise ValueError('Studio original provenance changed during capture')
    return digest,stamp


def _semantic(owner,value):
    from . import creative_derived_source as D,local_mask_state as M
    if value['region_mode']!='semantic_background':return None,None,None
    pc=_read(owner,'precompute','_precompute')
    if pc is None or getattr(pc,'backend',None)!='mediapipe':
        raise ValueError('Studio semantic background requires actual current-source portrait analysis')
    D.verify_precompute(owner,pc)
    if isinstance(owner,dict):
        backend=_read(owner,'precompute_backend','_precompute_backend')
        model=M.semantic_owner(pc,backend)
    else:model=M.current_owner(owner)
    if model is None or model!=M.semantic_owner(pc,pc.backend) or model!=value['semantic_owner']:
        raise ValueError('Studio background semantic model ownership changed')
    raw=np.asarray((getattr(pc,'masks',None) or {}).get('background'))
    if raw.dtype.kind!='f' or raw.ndim!=2 or not np.isfinite(raw).all() or np.any(raw<0) or np.any(raw>1):
        raise ValueError('Studio requires measured background confidence, not a silhouette or inferred floor')
    return raw,deepcopy(pc.input_source_binding),deepcopy(model)


def capture(owner,path=None,value=None):
    """Freeze recipe, original provenance and owned semantic input, not effects.

    Retained semantic intent needs valid model evidence even while disabled.
    An entirely unbound neutral recipe needs no frozen context or inference.
    """
    from .creative_document_host import memory_budget
    from . import local_mask_state as M
    source=_source(owner);value=validate(_value(owner) if value is None else value,source)
    if value['source'] is None:return None
    if path is None and not isinstance(owner,dict):path=owner._doc_path
    if not path:raise ValueError('Studio snapshot requires original-file provenance')
    original,before=_provenance(owner,path)
    raw,proof,model=_semantic(owner,value)
    mask=digest=None
    if raw is not None:
        if raw.size*8+8_388_608>memory_budget():raise ValueError('Studio semantic evidence exceeds memory budget')
        mask=np.array(raw,dtype=np.float32,copy=True);mask.setflags(write=False);digest=_hash(mask)
    context={'version':1,'source':deepcopy(source),'original_sha256':original,
        'recipe':value,'recipe_sha256':recipe_digest(value),'analysis':proof,
        'semantic_owner':model,'mask':mask,'mask_sha256':digest}
    verify_context(context,source,value)
    if M.file_stamp(path)!=before:raise ValueError('Studio original provenance changed during evidence capture')
    return context


def verify_context(context,source,value=None,path=None):
    from . import creative_derived_masks as C
    keys={'version','source','original_sha256','recipe','recipe_sha256','analysis','semantic_owner','mask','mask_sha256'}
    if (type(context) is not dict or set(context)!=keys or type(context['version']) is not int
            or context['version']!=1 or context['source']!=source):
        raise ValueError('Studio lacks its exact immutable source evidence')
    recipe=validate(context['recipe'],source)
    if recipe['source'] is None or recipe_digest(recipe)!=context['recipe_sha256']:
        raise ValueError('Studio captured recipe changed or has no retained source')
    if value is not None and validate(value,source)!=recipe:
        raise ValueError('Studio recipe differs from its captured evidence')
    semantic=recipe['region_mode']=='semantic_background'
    if recipe['semantic_owner']!=context['semantic_owner']:
        raise ValueError('Studio captured model differs from retained recipe ownership')
    if not semantic and (context['mask'] is not None or context['mask_sha256'] is not None):
        raise ValueError('Manual studio intent cannot retain a hidden semantic mask')
    C.verify_context({'version':1,'source':source,'original_sha256':context['original_sha256'],
        'analysis':context['analysis'],'semantic_owner':context['semantic_owner'],
        'fields':{'background':context['mask']} if semantic else {},
        'field_sha256':{'background':context['mask_sha256']} if semantic else {}},source,path=path)
    return context


def verify_snapshot(snapshot,path=None,shape=None):
    from . import creative_derived_source as D
    value=validate_state(snapshot)
    if D.record(snapshot) is None:
        if snapshot.get('creative_studio_context') is not None:
            raise ValueError('Derived studio evidence cannot be rebound to an original photo')
        return None
    source=_source(snapshot)
    if shape is not None and tuple(shape)!=(source['height'],source['width']):
        raise ValueError('Studio export must retain the complete immutable source grid')
    context=snapshot.get('creative_studio_context')
    if value['source'] is None:
        if context is not None:raise ValueError('Unbound neutral studio cannot retain stale evidence')
        return None
    return verify_context(context,source,value,path)


def preview(engine,value=None):
    """Prove actual pre-repair pixels and return an equality-safe review key."""
    from . import creative_derived_source as D,local_mask_state as M
    from . import studio_background_state as S,id_background_state as ID
    from .creative_derived_repair_runtime import verify_pipeline
    from .creative_derived_repairs import stack_digest
    source=_source(engine);value=validate(_value(engine) if value is None else value,source)
    if S.active(value) and (engine._vram.has_background() or ID.active(getattr(engine,'_id_background',None))):
        raise ValueError('Complete background replacement would overwrite studio adjustments')
    stamp=M.file_stamp(engine._doc_path)
    context=capture(engine,value=value);pipe=engine._vram
    evidence=verify_pipeline(pipe,source)
    if evidence['stack_sha256']!=stack_digest(engine):
        raise ValueError('Studio preview repair history differs from the current document')
    pixels=pipe.src_f32[0].permute(1,2,0).detach().cpu().numpy()
    expected=evidence['input'];proxy=D.analysis_rgb(engine)
    if (pixels.dtype!=np.float32 or pixels.shape!=(pipe.h,pipe.w,3)
            or list(pixels.shape)!=expected['shape'] or _hash(pixels)!=expected['sha256']
            or proxy.dtype!=np.uint8 or proxy.shape!=pixels.shape):
        raise ValueError('Studio measurement pixels differ from the owned immutable source')
    for y in range(0,pixels.shape[0],128):
        if not np.allclose(pixels[y:y+128],proxy[y:y+128].astype(np.float32)/255.,rtol=0,atol=np.finfo(np.float32).eps):
            raise ValueError('Studio measurement pixels differ from actual current-source analysis RGB')
    if context is None:
        original,checked_stamp=_provenance(engine,engine._doc_path)
        if checked_stamp!=stamp:raise ValueError('Studio original provenance changed during preview proof')
    else:original=context['original_sha256']
    D.verify(source,engine)
    # Even though measurement uses pre-repair pixels, the production review
    # contains repair output. Keep that exact evidence in the acceptance key.
    key=('creative-studio-v1',_json(source),recipe_digest(value),expected['sha256'],
         evidence['stack_sha256'],_json(evidence['output']),
         _json(None if context is None else context['analysis']),
         _json(None if context is None else context['semantic_owner']),
         None if context is None else context['mask_sha256'],original,stamp,id(pipe.src_f32))
    if M.file_stamp(engine._doc_path)!=stamp:raise ValueError('Studio original changed during preview verification')
    return context,pixels,key


def verify(engine,value):
    value=validate(value,_source(engine))
    preview(engine,value)
    return value


def verify_live(engine,value):
    return verify(engine,value)


def key(engine,value):
    return preview(engine,value)[2]


def semantic(engine,value):
    context,_,_=preview(engine,value)
    return None if context is None or context['mask'] is None else context['mask'].copy()


def _spec_context(spec):
    return verify_snapshot({'creative_base':getattr(spec,'creative_base',None),
        'studio_background':getattr(spec,'studio_background',None),
        'creative_studio_context':getattr(spec,'creative_studio_context',None)},
        path=getattr(spec,'studio_background_path',None))


def _proof(spec,pixels):
    from .creative_derived_repair_export import _pixels
    source=_source({'creative_base':getattr(spec,'creative_base',None)})
    context=_spec_context(spec)
    if context is None:return None
    return (source['sha256'],source['width'],source['height'],_pixels(source,pixels),
        context['recipe_sha256'],context['original_sha256'],context['mask_sha256'],
        _json(context['analysis']),_json(context['semantic_owner']))


def stamp_pixels(spec,pixels):
    """INTERNAL: immediately after canonical export_source, never after repair.

    This does not authenticate arbitrary caller pixels. Only the existing
    canonical export owner may create this ephemeral consumer stamp.
    """
    spec._creative_studio_resolved_pixels=_proof(spec,pixels)


def verify_export(spec,pixels,divisor=1.):
    """Require full float source; callers rerun full_semantic without resizing.

    The returned model owner must match the full-resolution segmenter's owner.
    Prepared effects continue through the ordinary studio stage unchanged.
    """
    context=_spec_context(spec)
    if context is None:return None
    if (type(divisor) not in (int,float) or divisor!=1.
            or getattr(spec,'_creative_studio_resolved_pixels',None)!=_proof(spec,pixels)):
        raise ValueError('Studio export differs from the canonical full-float pre-repair source')
    return context
