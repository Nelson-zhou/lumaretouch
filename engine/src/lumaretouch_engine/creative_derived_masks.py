"""Effective-source local masks; no physical-original raster or inference fallback."""
from copy import deepcopy
from hashlib import sha256
import numpy as np
from . import local_mask_state as M


def masks(snapshot,*,active_only=False):
    from . import local_grade_layers as L
    result=[row['mask'] for row in L.check(snapshot.get('local_grade_groups',snapshot.get('_local_grade_layers')))['layers'] if not active_only or row['enabled']]
    legacy=M.check(snapshot.get('local_masks',snapshot.get('_local_masks')))
    enabled=snapshot.get('grade_scope',snapshot.get('_grade_scope'))=='objects'
    if enabled or (not active_only and (legacy['source'] is not None or legacy['recipe']['objects'])):
        result.append(legacy)
    return result


def validate(mask,source):
    value=M.check(mask)
    if value['source'] is not None and value['source']!=source:
        raise ValueError('Local mask belongs to another effective source')
    if value['recipe']['objects'] and value['source']!=source:
        raise ValueError('Local objects require the current immutable source')
    M.R.validate_budget(value['recipe'],(source['height'],source['width']))
    return value


def _hash(value):
    digest=sha256()
    for row in value:digest.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return digest.hexdigest()


def capture(state_or_engine,values,path=None,*,active_values=None):
    from . import creative_derived_source as D
    from .creative_document_host import memory_budget
    source=D.binding(state_or_engine)
    values=[validate(value,source) for value in values]
    active=values if active_values is None else [validate(value,source) for value in active_values]
    channels=sorted({channel for value in active for channel in M.R.dependencies(value['recipe'])[1]})
    state=state_or_engine if isinstance(state_or_engine,dict) else None
    pc=state.get('_precompute') if state is not None else state_or_engine._precompute
    owner=M.owner_from_state(state) if state is not None else M.current_owner(state_or_engine)
    fields={};hashes={};proof=None
    if channels:
        from .semantic_sources import SOURCE_LABELS
        if any(channel not in SOURCE_LABELS for channel in channels):raise ValueError('Unknown derived semantic category')
        if pc is None or owner is None:raise ValueError('Derived semantic masks require actual current-source analysis')
        D.verify_precompute(state_or_engine,pc)
        proof=deepcopy(pc.input_source_binding)
        if any(M.R.dependencies(value['recipe'])[1] and value['semantic_owner']!=owner for value in active):
            raise ValueError('Derived mask semantic model ownership changed')
        raw=getattr(pc,'masks',{})
        if any(channel not in raw for channel in channels):raise ValueError('Derived semantic analysis lacks a required category')
        if sum(np.asarray(raw[c]).nbytes for c in channels)*2+8_388_608>memory_budget():
            raise ValueError('Derived semantic snapshot exceeds bounded memory')
        for channel in channels:
            value=np.asarray(raw[channel])
            if value.dtype.kind!='f' or value.ndim!=2 or not np.isfinite(value).all() or np.any(value<0) or np.any(value>1):
                raise ValueError('Derived semantic field is invalid')
            value=np.array(value,dtype=np.float32,copy=True);value.setflags(write=False)
            fields[channel]=value;hashes[channel]=_hash(value)
    if path is None and state is None:path=state_or_engine._doc_path
    if not path:raise ValueError('Derived local mask snapshot needs original provenance')
    return {'version':1,'source':source,'original_sha256':M.source_digest(path),
            'semantic_owner':deepcopy(owner) if channels else None,'analysis':proof,
            'fields':fields,'field_sha256':hashes}


def verify_context(context,source,values=(),path=None,*,active_values=None):
    keys={'version','source','original_sha256','semantic_owner','analysis','fields','field_sha256'}
    if type(context) is not dict or set(context)!=keys or context['version']!=1 or context['source']!=source:
        raise ValueError('Derived local masks lack their exact immutable source context')
    from .people_state import digest
    digest(context['original_sha256'])
    if path is not None and M.source_digest(path)!=context['original_sha256']:
        raise ValueError('Derived mask original-file provenance changed')
    fields=context['fields'];hashes=context['field_sha256']
    if type(fields) is not dict or type(hashes) is not dict or set(fields)!=set(hashes):raise ValueError('Invalid derived category bank')
    proof=context['analysis']
    if fields:
        from .semantic_sources import SOURCE_LABELS
        if any(channel not in SOURCE_LABELS for channel in fields):raise ValueError('Unknown derived semantic category')
        required={'sha256','width','height','proxy_width','proxy_height','proxy_sha256'}
        if type(proof) is not dict or set(proof)!=required or {k:proof.get(k) for k in ('sha256','width','height')}!=source:
            raise ValueError('Derived category analysis belongs to another source')
        digest(proof['proxy_sha256'])
        if any(type(proof[k]) is not int or proof[k]<1 for k in ('proxy_width','proxy_height')):raise ValueError('Invalid derived analysis extent')
        owner=context['semantic_owner'];prefix=M.SEMANTIC_CONTRACT+':'
        if type(owner) is not dict or set(owner)!={'backend','contract'} or owner['backend']!='mediapipe' or not owner['contract'].startswith(prefix):
            raise ValueError('Derived category model owner is missing or incompatible')
        digest(owner['contract'][len(prefix):])
    elif proof is not None or context['semantic_owner'] is not None:raise ValueError('Empty category bank has unexpected analysis')
    for channel,value in fields.items():
        if (type(value) is not np.ndarray or value.dtype!=np.float32 or value.ndim!=2
                or value.shape!=(proof.get('proxy_height'),proof.get('proxy_width'))
                or not np.isfinite(value).all() or np.any(value<0) or np.any(value>1) or _hash(value)!=hashes[channel]):
            raise ValueError('Derived semantic coverage changed after capture')
    for raw in values:validate(raw,source)
    for raw in values if active_values is None else active_values:
        value=validate(raw,source);channels=M.R.dependencies(value['recipe'])[1]
        if channels and (value['semantic_owner']!=context['semantic_owner'] or any(c not in fields for c in channels)):
            raise ValueError('Derived mask category or model evidence is missing')
    return context


def verify_snapshot(snapshot,path=None):
    from . import creative_derived_source as D
    if D.record(snapshot) is None:return None
    values=masks(snapshot)
    if not values:return None
    return verify_context(snapshot.get('creative_mask_context'),D.binding(snapshot),values,path,active_values=masks(snapshot,active_only=True))


def semantic_fields(mask,context,shape):
    verify_context(context,context['source'],[mask])
    from .face import _resize_float
    h,w=M.R._shape(shape)
    return {channel:_resize_float(context['fields'][channel],h,w)
            for channel in M.R.dependencies(mask['recipe'])[1]}


def _preview_pixels(engine):
    from . import creative_derived_source as D
    rgb=engine._vram.src_f32[0].permute(1,2,0).detach().cpu().numpy()
    proxy=D.analysis_rgb(engine)
    if rgb.dtype!=np.float32 or rgb.shape!=proxy.shape:
        raise ValueError('Local mask preview pixels differ from effective source')
    for y in range(0,rgb.shape[0],128):
        if not np.allclose(rgb[y:y+128],proxy[y:y+128].astype(np.float32)/255.,rtol=0,atol=np.finfo(np.float32).eps):
            raise ValueError('Local mask preview pixels differ from effective source')
    return rgb


def preview(engine,values,*,active_values=None):
    from . import creative_derived_source as D
    source=D.binding(engine);context=capture(engine,values,active_values=active_values);rgb=_preview_pixels(engine)
    D.verify(source,engine)
    return context,rgb


def prompted(mask,context,shape,*,engine=None,pixels=None,force=False,cancelled=lambda:False):
    from . import prompted_mask_resolver as P
    if not P.active(mask['recipe']):return {}
    if engine is not None:
        from .creative_derived_prompted import capture
        return P.fields(mask['recipe'],context['source'],None,shape,source_input=capture(engine),force=force,cancelled=cancelled)
    return P.fields(mask['recipe'],context['source'],None,shape,source_pixels=pixels,force=force,cancelled=cancelled)


def _pixels(spec,pixels):
    from . import creative_derived_source as D
    source=D.binding({'creative_base':spec.creative_base});context=verify_context(spec.creative_mask_context,source)
    value=np.asarray(pixels)
    if value.dtype!=np.float32 or value.shape!=(source['height'],source['width'],3):raise ValueError('Local mask export needs full derived float32 source')
    for row in value:
        if not np.isfinite(row).all() or np.any(row<0) or np.any(row>1):raise ValueError('Local mask source cannot silently clip HDR')
    return source['sha256'],_hash(value)


def stamp_pixels(spec,pixels):
    """Internal exporter boundary immediately after actual canonical decode."""
    spec._creative_mask_resolved_pixels=_pixels(spec,pixels)


def verify_pixels(spec,pixels):
    if getattr(spec,'_creative_mask_resolved_pixels',None)!=_pixels(spec,pixels):
        raise ValueError('Local mask pixels differ from canonical export-owned source')


def _dependencies(engine,values,*,active_values=None):
    """Hash actual retained analysis without copying it for every live gesture."""
    from . import creative_derived_source as D
    source=D.binding(engine);values=[validate(value,source) for value in values]
    active=values if active_values is None else [validate(value,source) for value in active_values]
    channels=sorted({c for value in active for c in M.R.dependencies(value['recipe'])[1]})
    owner=M.current_owner(engine);hashes={};proof=None
    if channels:
        pc=engine._precompute
        if pc is None or owner is None:raise ValueError('Derived local groups need current-source semantic analysis')
        D.verify_precompute(engine,pc);proof=deepcopy(pc.input_source_binding)
        for value in active:
            if M.R.dependencies(value['recipe'])[1] and value['semantic_owner']!=owner:
                raise ValueError('Derived local-group model owner changed')
        for channel in channels:
            value=np.asarray((getattr(pc,'masks',{}) or {}).get(channel))
            if value.ndim!=2 or value.dtype.kind!='f' or not np.isfinite(value).all() or np.any(value<0) or np.any(value>1):
                raise ValueError('Derived local-group category unavailable')
            hashes[channel]=_hash(value)
    return {'source':source,'analysis':proof,'semantic_owner':owner if channels else None,'field_sha256':hashes}


def live_dependencies(engine,groups):
    from . import local_grade_layers as L
    rows=L.check(groups)['layers']
    return _dependencies(engine,[row['mask'] for row in rows],active_values=[row['mask'] for row in rows if row['enabled']])


def cache_key(engine,values,recipe,*,active_values=None):
    """Validate actual inputs before reuse; no full semantic-bank allocation."""
    import json
    from . import prompted_mask_resolver as P,creative_derived_source as D
    source=D.binding(engine);dependencies=_dependencies(engine,values,active_values=active_values)
    rgb=_preview_pixels(engine)
    row=engine._docs[engine._doc_index];stamp=M.file_stamp(row['path'])
    if row.get('_local_source_stamp')!=stamp:
        raise ValueError('Original provenance changed after decoding')
    prompted=P.dependency_stamp() if any(P.active(value['recipe']) for value in (values if active_values is None else active_values)) else None
    D.verify(source,engine)
    return (json.dumps(recipe,sort_keys=True),json.dumps(dependencies,sort_keys=True),
            id(engine._vram.src_f32),_hash(rgb),stamp,json.dumps(prompted,sort_keys=True))


def sync_legacy(engine,*,strict=False):
    pipe=engine._vram;key=None
    try:
        value=M.check(engine._local_masks);key=cache_key(engine,[value],value)
        if getattr(pipe,'_local_mask_key',None)==key:
            pipe.grade_scope='objects'
            if strict and pipe.local_mask_suspended:raise ValueError(pipe.local_mask_suspended)
            return
        context,rgb=preview(engine,[value])
        fields=semantic_fields(value,context,(pipe.h,pipe.w))
        fields.update(prompted(value,context,(pipe.h,pipe.w),engine=engine))
        pipe.set_local_mask(M.R.raster(value['recipe'],(pipe.h,pipe.w),rgb=rgb,semantic=fields))
        pipe._local_mask_key=key
    except Exception as error:
        pipe.set_local_mask(np.zeros((pipe.h,pipe.w),np.uint8),reason=str(error));pipe._local_mask_key=key
        if strict:raise


def diagnostic_legacy(engine):
    pipe=engine._vram
    try:
        value=M.check(engine._local_masks);context,rgb=preview(engine,[value])
        fields=semantic_fields(value,context,(pipe.h,pipe.w))
        fields.update(prompted(value,context,(pipe.h,pipe.w),engine=engine))
        return M.R.raster(value['recipe'],(pipe.h,pipe.w),rgb=rgb,semantic=fields),None
    except Exception as error:return np.zeros((pipe.h,pipe.w),np.uint8),str(error)
