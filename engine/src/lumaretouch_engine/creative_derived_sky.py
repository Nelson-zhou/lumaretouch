"""Immutable-source evidence for the existing manual sky/recovery consumer.

Sky selection and recovery remain normalized vector intent. The existing stage
aligns them, the linked asset and its coverage through the actual image warp;
this adapter neither measures a substitute source nor copies the sky solver.
The physical photo is provenance, never the effective source or a semantic
fallback. Automatic sky proposals need their own canonical-input adapter and
are deliberately rejected here, including retained disabled proposals.
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
            raise ValueError('Sky state contains ambiguous '+public+' aliases')
        return owner.get(public,owner.get(private,default))
    return getattr(owner,private,default)


def _source(owner):
    from . import creative_derived_source as D
    if isinstance(owner,dict):_read(owner,'creative_base','_creative_base')
    if D.record(owner) is None:raise ValueError('Sky evidence requires an immutable creative source')
    return D.binding(owner)


def _value(owner):
    from . import sky_replacement_state as S
    return S.check(_read(owner,'sky_replacement','_sky_replacement'))


def _retained(value):
    from . import sky_replacement_state as S
    # Selecting an asset while disabled legitimately leaves source=None. Its
    # identity and the user's incomplete parameters must not silently vanish.
    return value!=S.empty()


def validate(value,source):
    """Validate all retained intent, without loading an asset or running ML."""
    from . import sky_replacement_state as S
    from .creative_derived_repairs import check_binding
    source=check_binding(source)
    if source is None:raise ValueError('Sky intent needs an immutable source extent')
    value=S.check(value)
    if value['source'] is not None and value['source']!=source:
        raise ValueError('Sky regions or recovery belong to another effective source')
    if value['semantic'] is not None:
        raise ValueError('Automatic sky selection has no immutable-source replay proof; explicitly remove or replace it with reviewed manual regions')
    S.validate_budget(value,(source['height'],source['width']))
    return value


def validate_state(owner):
    """Pure project/history validation; missing disabled links remain editable."""
    from . import creative_derived_source as D
    if isinstance(owner,dict):_read(owner,'creative_base','_creative_base')
    value=_value(owner)
    return value if D.record(owner) is None else validate(value,_source(owner))


def recipe_digest(value):
    from . import sky_replacement_state as S
    return sha256(_json(S.check(value)).encode('utf-8')).hexdigest()


def _provenance(owner,path):
    from . import local_mask_state as M
    before=M.file_stamp(path)
    if not isinstance(owner,dict):
        row=owner._docs[owner._doc_index]
        if row['path']!=path or row.get('_local_source_stamp')!=before:
            raise ValueError('Sky original-file provenance changed after decoding')
    original=M.source_digest(path)
    if M.file_stamp(path)!=before:raise ValueError('Sky original provenance changed during capture')
    return original,before


def _asset_stamp(value):
    from . import sky_replacement_state as S,sky_replacement_assets as A
    if not value['enabled']:return None
    S.ready(value)
    return A.verify(value['asset'])


def capture(owner,path=None,value=None):
    """Freeze intent and provenance, not raster masks or decoded sky pixels."""
    from . import local_mask_state as M
    source=_source(owner);value=validate(_value(owner) if value is None else value,source)
    if not _retained(value):return None
    if path is None and not isinstance(owner,dict):path=owner._doc_path
    if not path:raise ValueError('Sky snapshot requires original-file provenance')
    original,before=_provenance(owner,path)
    context={'version':1,'source':deepcopy(source),'original_sha256':original,
        'recipe':value,'recipe_sha256':recipe_digest(value),'asset_stamp':_asset_stamp(value)}
    verify_context(context,source,value)
    if M.file_stamp(path)!=before:raise ValueError('Sky original provenance changed during evidence capture')
    return context


def verify_context(context,source,value=None,path=None):
    from . import local_mask_state as M
    from .people_state import digest
    keys={'version','source','original_sha256','recipe','recipe_sha256','asset_stamp'}
    if (type(context) is not dict or set(context)!=keys or type(context['version']) is not int
            or context['version']!=1 or context['source']!=source):
        raise ValueError('Sky lacks its exact immutable source evidence')
    recipe=validate(context['recipe'],source)
    if not _retained(recipe) or recipe_digest(recipe)!=context['recipe_sha256']:
        raise ValueError('Sky captured recipe changed or has no retained intent')
    if value is not None and validate(value,source)!=recipe:
        raise ValueError('Sky recipe differs from its captured evidence')
    digest(context['original_sha256'])
    stamp=context['asset_stamp']
    if recipe['enabled']:
        if (type(stamp) is not tuple or len(stamp)!=5
                or any(type(n) is not int or n<0 for n in stamp)
                or _asset_stamp(recipe)!=stamp):
            raise ValueError('Sky linked asset changed after evidence capture')
    elif stamp is not None:
        raise ValueError('Disabled sky intent cannot retain an active asset stamp')
    if path is not None:
        before=M.file_stamp(path)
        if M.source_digest(path)!=context['original_sha256'] or M.file_stamp(path)!=before:
            raise ValueError('Sky original-file provenance changed')
    return context


def verify_snapshot(snapshot,path=None,shape=None):
    from . import creative_derived_source as D
    value=validate_state(snapshot)
    context=snapshot.get('creative_sky_context')
    if D.record(snapshot) is None:
        if context is not None:raise ValueError('Derived sky evidence cannot be rebound to an original photo')
        return None
    source=_source(snapshot)
    if shape is not None and tuple(shape)!=(source['height'],source['width']):
        raise ValueError('Sky export must retain the complete immutable source grid')
    if not _retained(value):
        if context is not None:raise ValueError('Neutral sky cannot retain stale evidence')
        return None
    return verify_context(context,source,value,path)


def _deformation_key(pipe):
    """Reuse the actual alignment owner's key, including all-person geometry."""
    from .mouth_shape_runtime import warp_key
    legacy=warp_key(pipe)
    prepared=getattr(pipe,'people_prepared',None)
    if prepared is None:return legacy,None
    delta=np.asarray(prepared.geometry.delta)
    if (delta.dtype!=np.float32 or delta.shape!=(1,pipe.h,pipe.w,2)
            or not np.isfinite(delta).all()):
        raise ValueError('Sky alignment lacks the actual current-source deformation field')
    return legacy,(_json(getattr(pipe,'people_key',None)),
        tuple(getattr(pipe,'people_origin',(0,0))),_hash(delta))


def preview(engine,value=None):
    """Prove the actual locator and repair output, not an ID-only source key.

    Returned pixels are the unwarped locator, not measured sky inputs. Existing
    SkyReplacementStage remains the only composition/alignment implementation.
    """
    from . import creative_derived_source as D,local_mask_state as M,id_background_state as ID
    from .creative_derived_repair_runtime import verify_pipeline
    from .creative_derived_repairs import stack_digest
    source=_source(engine);value=validate(_value(engine) if value is None else value,source)
    pipe=engine._vram
    if value['enabled'] and (pipe.has_background() or ID.active(getattr(engine,'_id_background',None))):
        raise ValueError('Complete background replacement would overwrite sky replacement')
    stamp=M.file_stamp(engine._doc_path)
    context=capture(engine,value=value)
    evidence=verify_pipeline(pipe,source)
    if evidence['stack_sha256']!=stack_digest(engine):
        raise ValueError('Sky preview repair history differs from the current document')
    pixels=pipe.src_f32[0].permute(1,2,0).detach().cpu().numpy()
    expected=evidence['input'];proxy=D.analysis_rgb(engine)
    if (pixels.dtype!=np.float32 or pixels.shape!=(pipe.h,pipe.w,3)
            or list(pixels.shape)!=expected['shape'] or _hash(pixels)!=expected['sha256']
            or proxy.dtype!=np.uint8 or proxy.shape!=pixels.shape):
        raise ValueError('Sky locator pixels differ from the owned immutable source')
    for y in range(0,pixels.shape[0],128):
        if not np.allclose(pixels[y:y+128],proxy[y:y+128].astype(np.float32)/255.,rtol=0,atol=np.finfo(np.float32).eps):
            raise ValueError('Sky locator pixels differ from actual current-source analysis RGB')
    if context is None:
        original,checked_stamp=_provenance(engine,engine._doc_path)
        if checked_stamp!=stamp:raise ValueError('Sky original provenance changed during preview proof')
    else:original=context['original_sha256']
    D.verify(source,engine)
    key=('creative-sky-v1',_json(source),recipe_digest(value),expected['sha256'],
        evidence['stack_sha256'],_json(evidence['output']),_deformation_key(pipe),
        original,stamp,None if context is None else context['asset_stamp'])
    if M.file_stamp(engine._doc_path)!=stamp:raise ValueError('Sky original changed during preview verification')
    if context is not None and value['enabled'] and M.file_stamp(value['asset']['path'])!=context['asset_stamp']:
        raise ValueError('Sky linked asset changed during preview verification')
    return context,pixels,key


def verify(engine,value):
    value=validate(value,_source(engine))
    preview(engine,value)
    return value


def verify_live(engine,value):
    return verify(engine,value)


def key(engine,value):
    return preview(engine,value)[2]


def _spec_context(spec):
    return verify_snapshot({'creative_base':getattr(spec,'creative_base',None),
        'sky_replacement':getattr(spec,'sky_replacement',None),
        'creative_sky_context':getattr(spec,'creative_sky_context',None)},
        path=getattr(spec,'sky_replacement_path',None))


def _proof(spec,pixels):
    from .creative_derived_repair_export import _pixels
    source=_source({'creative_base':getattr(spec,'creative_base',None)})
    context=_spec_context(spec)
    if context is None:return None
    return (source['sha256'],source['width'],source['height'],_pixels(source,pixels),
        context['recipe_sha256'],context['original_sha256'],context['asset_stamp'])


def stamp_pixels(spec,pixels):
    """INTERNAL: immediately after canonical export_source, before conversion.

    Only the canonical export owner may create this ephemeral consumer stamp.
    It is not a public mechanism for authenticating arbitrary caller pixels.
    """
    spec._creative_sky_resolved_pixels=_proof(spec,pixels)


def verify_export(spec,pixels,divisor=1.):
    """Require canonical full float RGB before any repair or output conversion.

    Full-grid manual fields and original-depth sky assets still use the existing
    prepare/stage path; neither proxy masks nor decoded preview assets substitute.
    """
    context=_spec_context(spec)
    if context is None:return None
    if (type(divisor) not in (int,float) or divisor!=1.
            or getattr(spec,'_creative_sky_resolved_pixels',None)!=_proof(spec,pixels)):
        raise ValueError('Sky export differs from the canonical full-float pre-repair source')
    return context
