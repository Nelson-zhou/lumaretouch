"""Measured fabric on immutable derived pixels; no original-mask fallback.

The existing OpenCV/torch fabric operator is unchanged. This module retains only
bounded semantic/scale evidence for an export snapshot, not in project history.
"""
from copy import deepcopy
from hashlib import sha256
import json
import numpy as np


def _hash(value):
    result=sha256()
    for row in value:result.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return result.hexdigest()


def _scale_vectors(pc):
    pool=getattr(pc,'all_landmarks',None) or [getattr(pc,'landmarks',None)]
    if len(pool)>256:raise ValueError('Fabric scale evidence exceeds face budget')
    vectors=[]
    for lm in pool:
        if lm is None:continue
        points=np.asarray(lm)
        if points.ndim==2 and len(points)>454:
            if points.shape[1]<2 or not np.isfinite(points[:,:2]).all():
                raise ValueError('Invalid measured fabric face scale')
            vectors.append(points[234,:2]-points[454,:2])
    return np.array(vectors,dtype=np.float64).reshape(-1,2)


def face_scale(context,h,w):
    vectors=context['scale_vectors']
    return max(1.,float(np.median(np.linalg.norm(vectors*[w,h],axis=1)))) if len(vectors) else None


def capture(state_or_engine,path=None):
    from . import creative_derived_source as D,local_mask_state as M
    from .creative_document_host import memory_budget
    state=state_or_engine if isinstance(state_or_engine,dict) else None
    pc=state.get('_precompute',state.get('precompute')) if state is not None else state_or_engine._precompute
    if pc is None or getattr(pc,'backend',None)!='mediapipe':
        raise ValueError('Derived fabric needs actual current-source portrait analysis')
    D.verify_precompute(state_or_engine,pc)
    owner=M.semantic_owner(pc,getattr(pc,'backend',None))
    if owner is None:raise ValueError('Derived fabric requires the pinned clothes model owner')
    raw=np.asarray((getattr(pc,'masks',{}) or {}).get('clothes'))
    if raw.dtype.kind!='f' or raw.ndim!=2 or not np.isfinite(raw).all() or np.any(raw<0) or np.any(raw>1):
        raise ValueError('Derived fabric needs measured clothes confidence, not a silhouette')
    if raw.size*8+8_388_608>memory_budget():raise ValueError('Derived fabric evidence exceeds memory budget')
    mask=np.array(raw,dtype=np.float32,copy=True);mask.setflags(write=False)
    vectors=_scale_vectors(pc);vectors.setflags(write=False)
    if path is None and state is None:path=state_or_engine._doc_path
    if not path:raise ValueError('Derived fabric requires original-file provenance')
    stamp=M.file_stamp(path)
    if state is None:
        row=state_or_engine._docs[state_or_engine._doc_index]
        if row.get('_local_source_stamp')!=stamp:
            raise ValueError('Fabric original-file provenance changed after decoding')
    original_sha256=M.source_digest(path)
    if M.file_stamp(path)!=stamp:raise ValueError('Fabric provenance changed during capture')
    context={'version':1,'source':D.binding(state_or_engine),'original_sha256':original_sha256,
        'analysis':deepcopy(pc.input_source_binding),'semantic_owner':owner,
        'mask':mask,'mask_sha256':_hash(mask),'scale_vectors':vectors,'scale_sha256':_hash(vectors)}
    return verify_context(context,context['source'])


def verify_context(context,source,path=None):
    from . import creative_derived_masks as C
    keys={'version','source','original_sha256','analysis','semantic_owner','mask','mask_sha256','scale_vectors','scale_sha256'}
    if type(context) is not dict or set(context)!=keys or context['version']!=1 or context['source']!=source:
        raise ValueError('Derived fabric lacks its exact immutable evidence')
    # Share the established six-class model/input/hash validation without
    # manufacturing a local-mask recipe or treating it as user selection.
    C.verify_context({'version':1,'source':source,'original_sha256':context['original_sha256'],
        'semantic_owner':context['semantic_owner'],'analysis':context['analysis'],
        'fields':{'clothes':context['mask']},'field_sha256':{'clothes':context['mask_sha256']}},source,path=path)
    vectors=context['scale_vectors']
    if (type(vectors) is not np.ndarray or vectors.dtype!=np.float64 or vectors.ndim!=2
            or vectors.shape[1]!=2 or len(vectors)>256 or not np.isfinite(vectors).all()
            or _hash(vectors)!=context['scale_sha256']):
        raise ValueError('Fabric measured face scale changed after capture')
    return context


def verify_snapshot(snapshot,path=None):
    from . import creative_derived_source as D
    from .fabric_stage import check_amount
    if D.record(snapshot) is None or not check_amount(snapshot.get('fabric_amount',snapshot.get('_fabric_amount',0))):return None
    return verify_context(snapshot.get('creative_fabric_context'),D.binding(snapshot),path)


def preview(engine):
    from . import creative_derived_source as D
    from .creative_derived_repair_runtime import verify_pipeline
    from .creative_derived_repairs import stack_digest
    context=capture(engine);pipe=engine._vram
    evidence=verify_pipeline(pipe,context['source'])
    if evidence['stack_sha256']!=stack_digest(engine):raise ValueError('Fabric repair history differs from current document')
    pixels=pipe.base()[0].permute(1,2,0).detach().cpu().numpy()
    expected=evidence['output'] or evidence['input']
    if list(pixels.shape)!=expected['shape'] or _hash(pixels)!=expected['sha256']:
        raise ValueError('Fabric pixels differ from the owned repaired source')
    D.verify(context['source'],engine)
    key=(json.dumps(context['source'],sort_keys=True),json.dumps(context['analysis'],sort_keys=True),
        json.dumps(context['semantic_owner'],sort_keys=True),context['mask_sha256'],context['scale_sha256'],
        evidence['stack_sha256'],expected['sha256'],context['original_sha256'])
    return context,pixels,key


def require_command(engine,request):
    from .fabric_stage import check_amount
    if (type(request) is not dict or request.get('cmd')!='fabric'
            or set(request)-{'cmd','action','amount','document_id'}
            or request.get('document_id')!=engine._load_id
            or request.get('action','set') not in ('set','clear')):
        raise ValueError('Invalid derived fabric command envelope')
    amount=check_amount(0. if request.get('action')=='clear' else request.get('amount'))
    if amount:preview(engine)


def _proof(spec,pixels):
    from . import creative_derived_source as D
    from .creative_derived_repair_export import _pixels
    source=D.binding({'creative_base':spec.creative_base})
    context=verify_context(getattr(spec,'creative_fabric_context',None),source)
    return (source['sha256'],_pixels(source,pixels),context['mask_sha256'],context['scale_sha256'],
        json.dumps(context['analysis'],sort_keys=True),json.dumps(context['semantic_owner'],sort_keys=True))


def stamp_pixels(spec,pixels):
    """INTERNAL: only immediately after canonical export_source resolution."""
    spec._creative_fabric_resolved_pixels=_proof(spec,pixels)


def export_pixels(spec,source,base,divisor):
    if divisor!=1. or getattr(spec,'_creative_fabric_resolved_pixels',None)!=_proof(spec,source):
        raise ValueError('Fabric export pixels differ from canonical full-float source')
    if getattr(spec,'repair',[]):
        from .creative_derived_repair_export import verify_replayed
        if base is None:raise ValueError('Fabric export lost its ordered repair replay')
        verify_replayed(spec,base)
        return base
    if base is not None:raise ValueError('Fabric export has an unowned replacement base')
    return source


def recovery_context(engine):
    """Read-only equality-safe proof for retained global recovery reviews."""
    from .fabric_stage import check_amount
    context,_,key=preview(engine)
    return {'version':1,'source':deepcopy(context['source']),
            'fabric_amount':check_amount(getattr(engine,'_fabric_amount',0)),
            'evidence_key':list(key)}
