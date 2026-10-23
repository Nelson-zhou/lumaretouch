"""Owned ID-background intent on the immutable returned creative source.

The original file is provenance, not a source for reviewed support or SAM.
Every retained independent review remains source-owned, including disabled and
unselected categories. Contexts contain only durable intent and bundle identity;
they never persist inferred alpha, decoded assets, or model-input rasters.
Existing support/native/stage owners still do all numerical composition.
"""
from copy import deepcopy
from hashlib import sha256
import json
import numpy as np


_UNSET = object()


def _json(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def _hash(value):
    result=sha256()
    for row in value:result.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return result.hexdigest()


def _read(owner,public,private,default=None):
    if isinstance(owner,dict):
        if public in owner and private in owner:
            raise ValueError('ID background state contains ambiguous '+public+' aliases')
        return owner.get(public,owner.get(private,default))
    return getattr(owner,private,default)


def _source(owner):
    from . import creative_derived_source as D
    if isinstance(owner,dict):_read(owner,'creative_base','_creative_base')
    if D.record(owner) is None:
        raise ValueError('ID background evidence requires an immutable creative source')
    return D.binding(owner)


def _supported_source(owner):
    """Inspect canonical bytes, never bless a matted/clipped display proxy.

    This bounded read-only admission check mirrors the existing native opaque
    SDR boundary. It does not convert, clip, matte or allocate full RGB pixels.
    Durable disabled intent remains editable because capture does not call it.
    """
    from . import creative_derived_source as D
    record=D.record(owner)
    if record is None:raise ValueError('ID background needs its actual immutable RGBA source')
    rgba=np.frombuffer(record['content'],dtype='<f4').reshape(-1,4)
    for offset in range(0,len(rgba),65536):
        block=rgba[offset:offset+65536]
        if (not np.isfinite(block).all() or np.any(block[:,3]!=1.)
                or np.any(block[:,:3]<0.) or np.any(block[:,:3]>1.)):
            raise ValueError('ID background requires opaque SDR source; no implicit alpha matte or HDR clipping')


def _value(owner):
    from . import id_background_state as S
    return S.check(_read(owner,'id_background','_id_background'))


def _retained(value):
    from . import id_background_state as S
    return value!=S.empty()


def validate(value,source):
    """Pure retained-intent check, with no file decoding or model dependency."""
    from . import id_background_state as S,local_mask_recipe as R
    from .creative_derived_repairs import check_binding
    source=check_binding(source)
    if source is None:raise ValueError('ID background intent needs an immutable source extent')
    value=S.check(value)
    if value['source'] is not None and value['source']!=source:
        raise ValueError('ID background reviews belong to another effective source')
    for category,binding in value['support'].items():
        if binding is None:continue
        mask=binding['mask']
        if mask['source']!=source:
            raise ValueError('ID background '+category+' review belongs to another effective source')
        # Validate all categories, not only the selected or currently visible one.
        # Existing support validation forbids generic semantic/full-image masks.
        R.validate_budget(mask['recipe'],(source['height'],source['width']))
    original_shadow=S.original_shadow_of(value)
    for role in ('lit_floor','retention'):
        binding=original_shadow[role]
        if binding is not None:
            if binding['mask']['source']!=source:
                raise ValueError('Original shadow samples belong to another effective source')
            R.validate_budget(binding['mask']['recipe'],(source['height'],source['width']))
    return value


def validate_state(owner):
    """Pure project/history validation; disabled prompts need no installed model."""
    from . import creative_derived_source as D
    if isinstance(owner,dict):
        _read(owner,'creative_base','_creative_base')
        _read(owner,'id_background_bundle','_id_background_bundle')
    value=_value(owner)
    return value if D.record(owner) is None else validate(value,_source(owner))


def recipe_digest(value):
    from . import id_background_state as S
    return sha256(_json(S.check(value)).encode('utf-8')).hexdigest()


def _asset_identity(value,bundle):
    """Identity comes from frozen bundle bytes, never a mutable linked path."""
    from . import id_background_assets as A
    asset=value['background']['asset']
    if asset is None:return None
    bundle=A.check_bundle(bundle)
    if bundle is None or bundle['binding']!=asset:
        raise ValueError('ID background retained asset differs from its immutable bundle')
    return {'binding':deepcopy(bundle['binding']),
            'byte_count':sum(len(chunk) for chunk in bundle['content'])}


def _check_asset_identity(value,identity):
    from . import id_background_state as S
    asset=value['background']['asset']
    if asset is None:
        if identity is not None:raise ValueError('ID background has hidden asset evidence')
        return
    if (type(identity) is not dict or set(identity)!={'binding','byte_count'}
            or S.asset(identity['binding'])!=asset
            or type(identity['byte_count']) is not int
            or not 0<identity['byte_count']<=S.MAX_ASSET_BYTES):
        raise ValueError('ID background lacks its exact retained immutable asset identity')


def _provenance(owner,path):
    from . import local_mask_state as M
    before=M.file_stamp(path)
    if not isinstance(owner,dict):
        row=owner._docs[owner._doc_index]
        if row['path']!=path or row.get('_local_source_stamp')!=before:
            raise ValueError('ID background original-file provenance changed after decoding')
    original=M.source_digest(path)
    if M.file_stamp(path)!=before:
        raise ValueError('ID background original provenance changed during capture')
    return original,before


def capture(owner,path=None,value=None):
    """Freeze intent, provenance and bundle identity, without model inference."""
    from . import local_mask_state as M
    source=_source(owner);value=validate(_value(owner) if value is None else value,source)
    if not _retained(value):return None
    if path is None and not isinstance(owner,dict):path=owner._doc_path
    if not path:raise ValueError('ID background snapshot requires original-file provenance')
    original,before=_provenance(owner,path)
    bundle=_read(owner,'id_background_bundle','_id_background_bundle')
    context={'version':1,'source':deepcopy(source),'original_sha256':original,
        'recipe':value,'recipe_sha256':recipe_digest(value),
        'asset_identity':_asset_identity(value,bundle)}
    verify_context(context,source,value,bundle=bundle)
    if M.file_stamp(path)!=before:
        raise ValueError('ID background original provenance changed during evidence capture')
    return context


def verify_context(context,source,value=None,path=None,bundle=_UNSET):
    from . import local_mask_state as M
    from .people_state import digest
    keys={'version','source','original_sha256','recipe','recipe_sha256','asset_identity'}
    if (type(context) is not dict or set(context)!=keys or type(context['version']) is not int
            or context['version']!=1 or context['source']!=source):
        raise ValueError('ID background lacks its exact immutable source evidence')
    recipe=validate(context['recipe'],source)
    if not _retained(recipe) or recipe_digest(recipe)!=context['recipe_sha256']:
        raise ValueError('ID background captured recipe changed or has no retained intent')
    if value is not None and validate(value,source)!=recipe:
        raise ValueError('ID background recipe differs from its captured evidence')
    digest(context['original_sha256'])
    _check_asset_identity(recipe,context['asset_identity'])
    if bundle is not _UNSET and _asset_identity(recipe,bundle)!=context['asset_identity']:
        raise ValueError('ID background immutable bundle changed after evidence capture')
    if path is not None:
        before=M.file_stamp(path)
        if M.source_digest(path)!=context['original_sha256'] or M.file_stamp(path)!=before:
            raise ValueError('ID background original-file provenance changed')
    return context


def verify_snapshot(snapshot,path=None,shape=None):
    from . import creative_derived_source as D
    value=validate_state(snapshot)
    context=snapshot.get('creative_id_background_context')
    if D.record(snapshot) is None:
        if context is not None:
            raise ValueError('Derived ID background evidence cannot be rebound to an original photo')
        return None
    source=_source(snapshot)
    if shape is not None and tuple(shape)!=(source['height'],source['width']):
        raise ValueError('ID background export must retain the complete immutable source grid')
    if not _retained(value):
        if context is not None:raise ValueError('Neutral ID background cannot retain stale evidence')
        return None
    bundle=_read(snapshot,'id_background_bundle','_id_background_bundle')
    return verify_context(context,source,value,path,bundle)


def _deformation_key(pipe):
    from .mouth_shape_runtime import warp_key
    legacy=warp_key(pipe)
    prepared=getattr(pipe,'people_prepared',None)
    if prepared is None:return legacy,None
    delta=np.asarray(prepared.geometry.delta)
    if (delta.dtype!=np.float32 or delta.shape!=(1,pipe.h,pipe.w,2)
            or not np.isfinite(delta).all()):
        raise ValueError('ID background alignment lacks its actual current-source deformation field')
    return legacy,(_json(getattr(pipe,'people_key',None)),
        tuple(getattr(pipe,'people_origin',(0,0))),_hash(delta))


def _activity_key(engine):
    """Read current activation on every lookup, before accepting a cached field."""
    from . import sky_replacement_state as SKY,studio_background_state as ST
    return (bool(engine._vram.has_background()),
        bool((getattr(engine,'_bg',None) or {}).get('active')),
        SKY.check(getattr(engine,'_sky_replacement',None))['enabled'],
        ST.active(getattr(engine,'_studio_background',None)))


def _prompted_key(engine,value,source):
    from . import id_background_state as S,prompted_mask_resolver as P
    from . import creative_derived_prompted as Q
    if not S.active(value):return None
    support=value['support'][value['selected_support']]
    objects=[] if support is None else P.active(support['mask']['recipe'])
    if not objects:return None
    packet=Q.capture(engine)
    identity=Q.cache_identity(packet,source)
    if any(obj['selection']['input_sha256']!=packet['descriptor']['input_sha256'] for obj in objects):
        raise ValueError('ID background prompted review belongs to another immutable model input')
    return identity,_json(P.dependency_stamp())


def preview(engine,value=None):
    """Prove the actual pre-repair locator and the complete rendered review key."""
    from . import creative_derived_source as D,local_mask_state as M,id_background_state as S
    from .creative_derived_repair_runtime import verify_pipeline
    from .creative_derived_repairs import stack_digest
    source=_source(engine);value=validate(_value(engine) if value is None else value,source)
    _supported_source(engine)
    pipe=engine._vram;activity=_activity_key(engine)
    if S.active(value) and any(activity):
        raise ValueError('Complete background replacement would overwrite another active background effect')
    stamp=M.file_stamp(engine._doc_path)
    context=capture(engine,value=value)
    evidence=verify_pipeline(pipe,source)
    if evidence['stack_sha256']!=stack_digest(engine):
        raise ValueError('ID background preview repair history differs from the current document')
    pixels=pipe.src_f32[0].permute(1,2,0).detach().cpu().numpy()
    expected=evidence['input'];proxy=D.analysis_rgb(engine)
    if (pixels.dtype!=np.float32 or pixels.shape!=(pipe.h,pipe.w,3)
            or list(pixels.shape)!=expected['shape'] or _hash(pixels)!=expected['sha256']
            or proxy.dtype!=np.uint8 or proxy.shape!=pixels.shape):
        raise ValueError('ID background locator pixels differ from the owned immutable source')
    for y in range(0,pixels.shape[0],128):
        if not np.allclose(pixels[y:y+128],proxy[y:y+128].astype(np.float32)/255.,rtol=0,atol=np.finfo(np.float32).eps):
            raise ValueError('ID background locator differs from actual current-source analysis RGB')
    if context is None:
        original,checked_stamp=_provenance(engine,engine._doc_path)
        if checked_stamp!=stamp:
            raise ValueError('ID background original provenance changed during preview proof')
    else:original=context['original_sha256']
    prompted=_prompted_key(engine,value,source)
    D.verify(source,engine)
    key=('creative-id-background-v1',_json(source),recipe_digest(value),expected['sha256'],
        evidence['stack_sha256'],_json(evidence['output']),_deformation_key(pipe),activity,
        original,stamp,_json(None if context is None else context['asset_identity']),
        prompted,id(pipe.src_f32))
    if M.file_stamp(engine._doc_path)!=stamp:
        raise ValueError('ID background original changed during preview verification')
    if context is not None:
        verify_context(context,source,value,bundle=getattr(engine,'_id_background_bundle',None))
    if _activity_key(engine)!=activity:
        raise ValueError('ID background activation changed during preview verification')
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
        'id_background':getattr(spec,'id_background',None),
        'id_background_bundle':getattr(spec,'id_background_bundle',None),
        'creative_id_background_context':getattr(spec,'creative_id_background_context',None)},
        path=getattr(spec,'id_background_path',None))


def _proof(spec,pixels):
    from .creative_derived_repair_export import _pixels
    source=_source({'creative_base':getattr(spec,'creative_base',None)})
    context=_spec_context(spec)
    if context is None:return None
    _supported_source({'creative_base':getattr(spec,'creative_base',None)})
    return (source['sha256'],source['width'],source['height'],_pixels(source,pixels),
        context['recipe_sha256'],context['original_sha256'],_json(context['asset_identity']))


def stamp_pixels(spec,pixels):
    """INTERNAL: canonical export owner calls before repair or quantization.

    This ephemeral stamp does not authenticate arbitrary caller pixels and is
    not a durable substitute for the actual content-addressed creative asset.
    """
    spec._creative_id_background_resolved_pixels=_proof(spec,pixels)


def verify_export(spec,pixels,divisor=1.):
    """Require exact canonical full float RGB before ID-background prepare."""
    context=_spec_context(spec)
    if context is None:return None
    if (type(divisor) not in (int,float) or divisor!=1.
            or getattr(spec,'_creative_id_background_resolved_pixels',None)!=_proof(spec,pixels)):
        raise ValueError('ID background export differs from the canonical full-float pre-repair source')
    return context
